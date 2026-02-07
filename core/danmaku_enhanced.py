# -*- coding: utf-8 -*-
"""
改进的弹幕客户端
添加断线重连、更好的错误处理和日志
"""

import asyncio
import time
from typing import Optional, Callable

from core.danmaku import DanmakuClient as OriginalDanmakuClient
from core.logger import get_logger
from core.config import get_config
from core.performance import performance_monitor

logger = get_logger("danmaku_enhanced")


class EnhancedDanmakuClient(OriginalDanmakuClient):
    """增强版弹幕客户端"""
    
    def __init__(self, room_id: int, cookies: Optional[dict] = None):
        super().__init__(room_id, cookies)
        
        # 重连配置
        self.enable_auto_reconnect = get_config('reconnect.enable_auto_reconnect', True)
        self.max_retries = get_config('reconnect.max_retries', 5)
        self.retry_delay = get_config('reconnect.retry_delay_seconds', 5)
        self.exponential_backoff = get_config('reconnect.exponential_backoff', True)
        
        # 重连状态
        self.retry_count = 0
        self.is_reconnecting = False
        self.reconnect_task = None
        
        # 回调函数
        self.on_reconnect_start: Optional[Callable] = None
        self.on_reconnect_success: Optional[Callable] = None
        self.on_reconnect_failed: Optional[Callable] = None
    
    async def connect(self):
        """连接到直播间（带重试）"""
        try:
            logger.info(f"正在连接到直播间 {self.room_id}")
            success = await super().connect()
            
            if success:
                self.retry_count = 0
                logger.info(f"成功连接到直播间 {self.room_id}")
                return True
            else:
                logger.error(f"连接到直播间 {self.room_id} 失败")
                return False
        
        except Exception as e:
            logger.error(f"连接到直播间 {self.room_id} 时发生异常: {e}", exc_info=True)
            return False
    
    async def auto_reconnect(self):
        """自动重连"""
        if not self.enable_auto_reconnect:
            logger.info("自动重连已禁用")
            return False
        
        if self.is_reconnecting:
            logger.warning("已经在重连中，跳过")
            return False
        
        self.is_reconnecting = True
        
        if self.on_reconnect_start:
            try:
                await self.on_reconnect_start()
            except Exception as e:
                logger.error(f"重连开始回调失败: {e}")
        
        while self.retry_count < self.max_retries:
            self.retry_count += 1
            
            # 计算延迟时间
            if self.exponential_backoff:
                delay = min(self.retry_delay * (2 ** (self.retry_count - 1)), 60)
            else:
                delay = self.retry_delay
            
            logger.info(f"第 {self.retry_count}/{self.max_retries} 次重连尝试，"
                       f"等待 {delay} 秒...")
            
            await asyncio.sleep(delay)
            
            try:
                success = await self.connect()
                
                if success:
                    logger.info("重连成功")
                    self.is_reconnecting = False
                    self.retry_count = 0
                    
                    if self.on_reconnect_success:
                        try:
                            await self.on_reconnect_success()
                        except Exception as e:
                            logger.error(f"重连成功回调失败: {e}")
                    
                    return True
            
            except Exception as e:
                logger.error(f"重连尝试失败: {e}", exc_info=True)
        
        logger.error(f"重连失败，已达到最大重试次数 {self.max_retries}")
        self.is_reconnecting = False
        
        if self.on_reconnect_failed:
            try:
                await self.on_reconnect_failed()
            except Exception as e:
                logger.error(f"重连失败回调失败: {e}")
        
        return False
    
    async def _receive_loop(self):
        """改进的消息接收循环"""
        try:
            while self.running:
                try:
                    data = await self.ws.recv()
                    
                    # 记录处理开始时间
                    start_time = time.time()
                    
                    # 将接收到的数据追加到缓冲区
                    self.buffer.extend(data)
                    
                    # 处理缓冲区中的数据
                    await self._handle_packet(self.buffer)
                    
                    # 记录处理时间
                    processing_time = time.time() - start_time
                    performance_monitor.record_danmaku_processing(processing_time)
                
                except asyncio.CancelledError:
                    logger.info("接收循环被取消")
                    break
                
                except Exception as e:
                    if self.running:
                        logger.error(f"接收数据错误: {e}", exc_info=True)
                        performance_monitor.record_error()
                        
                        # 如果是连接错误，尝试重连
                        if "closed" in str(e).lower() or "disconnect" in str(e).lower():
                            logger.warning("检测到连接断开，尝试重连")
                            self.running = False
                            
                            # 启动重连任务
                            if self.enable_auto_reconnect:
                                self.reconnect_task = asyncio.create_task(self.auto_reconnect())
                            break
        
        except Exception as e:
            logger.error(f"接收循环错误: {e}", exc_info=True)
            self.running = False
        
        finally:
            # 清理缓冲区
            self.buffer.clear()
    
    async def disconnect(self):
        """断开连接"""
        logger.info(f"正在断开与直播间 {self.room_id} 的连接")
        
        # 取消重连任务
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass
        
        await super().disconnect()
        logger.info(f"已断开与直播间 {self.room_id} 的连接")
    
    async def _handle_danmaku(self, msg: dict):
        """处理弹幕消息（带错误处理）"""
        try:
            await super()._handle_danmaku(msg)
        except KeyError as e:
            logger.error(f"弹幕数据缺少必要字段: {e}, 数据: {msg}")
        except Exception as e:
            logger.error(f"处理弹幕错误: {e}", exc_info=True)
    
    async def _handle_gift(self, msg: dict):
        """处理礼物消息（带错误处理）"""
        try:
            await super()._handle_gift(msg)
        except KeyError as e:
            logger.error(f"礼物数据缺少必要字段: {e}, 数据: {msg}")
        except Exception as e:
            logger.error(f"处理礼物错误: {e}", exc_info=True)
    
    async def _handle_superchat(self, msg: dict):
        """处理SC消息（带错误处理）"""
        try:
            await super()._handle_superchat(msg)
        except KeyError as e:
            logger.error(f"SC数据缺少必要字段: {e}, 数据: {msg}")
        except Exception as e:
            logger.error(f"处理SC错误: {e}", exc_info=True)
    
    async def _handle_guard(self, msg: dict):
        """处理上舰消息（带错误处理）"""
        try:
            await super()._handle_guard(msg)
        except KeyError as e:
            logger.error(f"上舰数据缺少必要字段: {e}, 数据: {msg}")
        except Exception as e:
            logger.error(f"处理上舰错误: {e}", exc_info=True)
    
    async def _handle_interact(self, msg: dict):
        """处理互动消息（带错误处理）"""
        try:
            await super()._handle_interact(msg)
        except KeyError as e:
            logger.error(f"互动数据缺少必要字段: {e}, 数据: {msg}")
        except Exception as e:
            logger.error(f"处理互动错误: {e}", exc_info=True)
