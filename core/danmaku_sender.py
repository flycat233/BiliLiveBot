# -*- coding: utf-8 -*-
"""
B站弹幕发送模块
实现发送弹幕、管理发送频率等功能
"""

import time
import random
import asyncio
from typing import Dict, Optional
from pathlib import Path

import httpx
from core.wbi_sign import sign_params


class DanmakuSender:
    """B站弹幕发送器"""
    
    # 发送弹幕 API
    SEND_URL = "https://api.live.bilibili.com/msg/send"
    
    def __init__(self, cookies: Dict, room_id: int):
        """
        初始化弹幕发送器
        
        Args:
            cookies: 登录 Cookie
            room_id: 直播间 ID
        """
        self.cookies = cookies
        self.room_id = room_id
        self.csrf_token = self._get_csrf_token()
        
        # 发送历史（防止刷屏）
        self.send_history = []
        self.last_send_time = 0
        
        # 默认配置
        self.min_interval = 3  # 最小发送间隔（秒）
        self.max_length = 40  # 最大发送长度（B站限制）
        self.max_duplicate = 3  # 最大重复次数
    
    def _get_csrf_token(self) -> str:
        """
        从 Cookie 中获取 CSRF Token
        
        Returns:
            str: CSRF Token
        """
        return self.cookies.get("bili_jct", "")
    
    async def send(self, message: str, **kwargs) -> Dict:
        """
        发送弹幕

        Args:
            message: 弹幕内容
            **kwargs: 其他参数（如 color, mode 等）

        Returns:
            Dict: 发送结果
        """
        # 检查是否登录
        if not self.cookies or not self.csrf_token:
            return {
                "success": False,
                "message": "未登录或缺少 CSRF Token"
            }

        # 检查发送间隔
        current_time = time.time()
        if current_time - self.last_send_time < self.min_interval:
            wait_time = self.min_interval - (current_time - self.last_send_time)
            return {
                "success": False,
                "message": f"发送过于频繁，请等待 {wait_time:.1f} 秒"
            }

        # 检查消息长度
        if len(message) > self.max_length:
            return {
                "success": False,
                "message": f"消息过长，最大支持 {self.max_length} 个字符"
            }

        # 检查重复
        if self._is_duplicate(message):
            return {
                "success": False,
                "message": "消息重复，请稍后再试"
            }

        try:
            # 构建参数
            params = {
                "bubble": kwargs.get("bubble", 0),
                "msg": message,
                "roomid": self.room_id,
                "rnd": int(time.time()),
                "color": kwargs.get("color", 16777215),  # 白色
                "mode": kwargs.get("mode", 1),  # 普通弹幕
                "fontsize": kwargs.get("fontsize", 25),
                "csrf": self.csrf_token,
                "csrf_token": self.csrf_token
            }

            # WBI 签名
            params = await sign_params(params)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"https://live.bilibili.com/{self.room_id}",
                "Origin": "https://live.bilibili.com",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site"
            }

            async with httpx.AsyncClient(cookies=self.cookies) as client:
                response = await client.post(
                    self.SEND_URL,
                    data=params,
                    headers=headers,
                    timeout=10.0
                )

                data = response.json()

                if data.get("code") == 0:
                    # 发送成功，记录历史
                    self.send_history.append({
                        "message": message,
                        "time": current_time
                    })
                    self.last_send_time = current_time

                    # 清理旧的历史记录（保留最近10条）
                    if len(self.send_history) > 10:
                        self.send_history = self.send_history[-10:]

                    return {
                        "success": True,
                        "message": "发送成功"
                    }
                else:
                    return {
                        "success": False,
                        "message": data.get("message", "发送失败")
                    }

        except Exception as e:
            return {
                "success": False,
                "message": f"发送失败: {str(e)}"
            }
    
    def _is_duplicate(self, message: str) -> bool:
        """
        检查消息是否重复
        
        Args:
            message: 消息内容
            
        Returns:
            bool: 是否重复
        """
        # 清理最近的历史记录（保留5分钟内的）
        current_time = time.time()
        self.send_history = [
            item for item in self.send_history
            if current_time - item["time"] < 300
        ]
        
        # 统计相同消息的数量
        count = sum(1 for item in self.send_history if item["message"] == message)
        
        return count >= self.max_duplicate
    
    async def send_with_random_delay(self, message: str, min_delay: float = 1.0, 
                                   max_delay: float = 3.0, **kwargs) -> Dict:
        """
        带随机延迟的发送弹幕
        
        Args:
            message: 弹幕内容
            min_delay: 最小延迟（秒）
            max_delay: 最大延迟（秒）
            **kwargs: 其他参数
            
        Returns:
            Dict: 发送结果
        """
        # 随机延迟
        delay = random.uniform(min_delay, max_delay)
        await asyncio.sleep(delay)
        
        return await self.send(message, **kwargs)
    
    def set_config(self, min_interval: Optional[int] = None, 
                   max_length: Optional[int] = None, 
                   max_duplicate: Optional[int] = None):
        """
        设置发送配置
        
        Args:
            min_interval: 最小发送间隔
            max_length: 最大消息长度
            max_duplicate: 最大重复次数
        """
        if min_interval is not None:
            self.min_interval = min_interval
        if max_length is not None:
            self.max_length = max_length
        if max_duplicate is not None:
            self.max_duplicate = max_duplicate
    
    def get_status(self) -> Dict:
        """
        获取发送器状态
        
        Returns:
            Dict: 状态信息
        """
        return {
            "room_id": self.room_id,
            "csrf_token": bool(self.csrf_token),
            "min_interval": self.min_interval,
            "max_length": self.max_length,
            "max_duplicate": self.max_duplicate,
            "send_history_count": len(self.send_history),
            "last_send_time": self.last_send_time
        }


# 全局发送器实例
_danmaku_sender: Optional[DanmakuSender] = None


def init_danmaku_sender(cookies: Dict, room_id: int) -> DanmakuSender:
    """
    初始化全局弹幕发送器
    
    Args:
        cookies: 登录 Cookie
        room_id: 直播间 ID
        
    Returns:
        DanmakuSender: 发送器实例
    """
    global _danmaku_sender
    _danmaku_sender = DanmakuSender(cookies, room_id)
    return _danmaku_sender


def get_danmaku_sender() -> Optional[DanmakuSender]:
    """
    获取全局弹幕发送器
    
    Returns:
        Optional[DanmakuSender]: 发送器实例
    """
    return _danmaku_sender


async def send_danmaku(message: str, **kwargs) -> Dict:
    """
    发送弹幕（使用全局发送器）
    
    Args:
        message: 弹幕内容
        **kwargs: 其他参数
        
    Returns:
        Dict: 发送结果
    """
    if _danmaku_sender is None:
        return {
            "success": False,
            "message": "弹幕发送器未初始化"
        }
    
    return await _danmaku_sender.send(message, **kwargs)