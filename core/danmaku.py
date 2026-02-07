# -*- coding: utf-8 -*-
"""
B站直播弹幕客户端
实现 WebSocket 连接、弹幕接收、消息解析等功能
"""

import asyncio
import json
import struct
import zlib
from typing import Optional, Dict, Callable
from enum import IntEnum

import httpx
import websockets

from core.wbi_sign import sign_params
from core.interact_word_v2_parser import parse_interact_word_v2


class Operation(IntEnum):
    """B站直播协议操作码"""
    HANDSHAKE = 0  # 客户端发送认证包
    HANDSHAKE_REPLY = 1  # 服务器回复认证包
    HEARTBEAT = 2  # 客户端发送心跳包
    HEARTBEAT_REPLY = 3  # 服务器回复心跳包
    SEND_MSG = 4  # 客户端发送消息
    SEND_MSG_REPLY = 5  # 服务器推送消息
    DISCONNECT_REPLY = 6  # 服务器通知客户端断开连接
    AUTH = 7  # 认证包
    AUTH_REPLY = 8  # 认证回复
    RAW = 9  # 原始数据
    PROTO_READY = 10  # 协议就绪
    PROTO_FINISH = 11  # 协议完成
    CHANGE_ROOM = 12  # 切换房间
    CHANGE_ROOM_REPLY = 13  # 切换房间回复
    REGISTER = 14  # 注册
    REGISTER_REPLY = 15  # 注册回复
    UNREGISTER = 16  # 注销
    UNREGISTER_REPLY = 17  # 注销回复


class PacketHeader:
    """数据包头部"""
    HEADER_STRUCT = struct.Struct('>I2H2I')
    
    def __init__(self, packet_length: int, header_length: int, protocol_version: int,
                 operation: int, sequence_id: int):
        self.packet_length = packet_length
        self.header_length = header_length
        self.protocol_version = protocol_version
        self.operation = operation
        self.sequence_id = sequence_id
    
    @classmethod
    def from_bytes(cls, data: bytes):
        """从字节流解析包头"""
        try:
            # 确保数据长度足够
            if len(data) < 16:
                raise ValueError("数据长度不足")
            
            # 解析包头
            fields = cls.HEADER_STRUCT.unpack(data[:16])
            return cls(*fields)
        except struct.error as e:
            # 如果解析失败，尝试使用小端序
            try:
                fields = struct.Struct('<I2H2I').unpack(data[:16])
                return cls(*fields)
            except:
                raise ValueError(f"解析包头失败: {e}")
    
    def to_bytes(self) -> bytes:
        """转换为字节流"""
        return self.HEADER_STRUCT.pack(
            self.packet_length,
            self.header_length,
            self.protocol_version,
            self.operation,
            self.sequence_id
        )


class DanmakuClient:
    """B站直播弹幕客户端"""
    
    # WebSocket 服务器地址
    WS_URL = "wss://broadcastlv.chat.bilibili.com/sub"

    # 直播间信息 API
    ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
    # 使用旧端点，不需要 WBI 签名
    DANMU_INFO_URL = "https://api.live.bilibili.com/room/v1/Danmu/getConf"
    
    def __init__(self, room_id: int, cookies: Optional[Dict] = None):
        """
        初始化弹幕客户端
        
        Args:
            room_id: 直播间 ID
            cookies: 登录 Cookie（可选）
        """
        self.room_id = room_id
        self.cookies = cookies or {}
        self.real_room_id = room_id  # 真实房间号

        self.ws = None
        self.running = False
        self.auto_reconnect = True  # 启用自动重连
        self.max_reconnect_attempts = 5  # 最大重连次数
        self.reconnect_attempts = 0  # 当前重连次数
        self.heartbeat_task = None
        self.receive_task = None
        self.reconnect_task = None  # 重连任务

        # 消息回调函数
        self.on_danmaku: Optional[Callable] = None
        self.on_gift: Optional[Callable] = None
        self.on_superchat: Optional[Callable] = None
        self.on_guard: Optional[Callable] = None
        self.on_interact: Optional[Callable] = None
        self.on_online: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None  # 断开连接回调

        # 数据包缓冲区
        self.buffer = bytearray()

        # HTTP客户端（连接池）
        self.http_client: Optional[httpx.AsyncClient] = None

        # 用户检测相关
        self.user_first_seen = {}  # 记录用户首次出现 {uid: {"name": str, "time": float, "source": str}}
        self.user_enter_history = set()  # 记录已进入的用户 {uid:name}
    
    async def connect(self):
        """连接到直播间"""
        try:
            # 创建HTTP客户端（连接池）
            self.http_client = httpx.AsyncClient(
                cookies=self.cookies,
                timeout=httpx.Timeout(5.0, connect=3.0)  # 优化超时时间
            )
            
            # 并行获取真实房间号和弹幕服务器信息
            print(f"正在获取房间信息...")
            room_id_task = asyncio.create_task(self._get_real_room_id())
            
            # 等待房间号获取完成
            await room_id_task
            
            if not self.real_room_id:
                print("无法获取真实房间号，连接失败")
                return False

            # 获取弹幕服务器信息
            danmu_info = await self._get_danmu_info()

            if not danmu_info:
                print("无法获取弹幕服务器信息，连接失败")
                return False

            # 连接 WebSocket，优化超时设置
            print(f"正在连接 WebSocket 服务器...")
            try:
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        self.WS_URL,
                        ping_interval=30,
                        ping_timeout=10,
                        close_timeout=1
                    ),
                    timeout=5.0  # 从10秒优化到5秒
                )
                print(f"WebSocket 连接成功")
            except asyncio.TimeoutError:
                print("WebSocket 连接超时")
                return False

            # 发送认证包
            token = danmu_info.get("token", "")
            await self._send_auth(token)

            # 等待认证回复，优化超时时间
            try:
                auth_reply = await asyncio.wait_for(self.ws.recv(), timeout=3.0)  # 从5秒优化到3秒
                await self._handle_packet(auth_reply)
            except asyncio.TimeoutError:
                print("等待认证回复超时")
                if self.ws:
                    await self.ws.close()
                return False

            # 检查连接是否仍然有效
            # websockets 16.0+ 使用 state 属性而不是 closed
            try:
                from websockets.protocol import State
                if self.ws and hasattr(self.ws, 'state') and self.ws.state != State.OPEN:
                    print("认证失败，连接已关闭")
                    return False
            except ImportError:
                # 兼容旧版本 websockets
                if self.ws and hasattr(self.ws, 'closed') and self.ws.closed:
                    print("认证失败，连接已关闭")
                    return False

            # 初始化缓冲区
            self.buffer = bytearray()

            self.running = True

            # 启动心跳和接收循环
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self.receive_task = asyncio.create_task(self._receive_loop())

            print(f"已连接到直播间 {self.real_room_id}")
            return True
        except Exception as e:
            print(f"连接失败: {e}")
            import traceback
            traceback.print_exc()

            # 确保在失败时清理所有状态
            self.running = False
            if self.ws:
                try:
                    await self.ws.close()
                except:
                    pass
                self.ws = None
            self.heartbeat_task = None
            self.receive_task = None

            return False
    
    async def disconnect(self):
        """断开连接"""
        # 先设置运行标志为 False
        self.running = False
        self.auto_reconnect = False  # 禁用自动重连

        # 取消任务并等待它们完成
        tasks = []
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            tasks.append(self.heartbeat_task)
        if self.receive_task and not self.receive_task.done():
            self.receive_task.cancel()
            tasks.append(self.receive_task)
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()
            tasks.append(self.reconnect_task)

        # 等待任务取消
        if tasks:
            try:
                await asyncio.wait(tasks, timeout=3.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                print("警告: 部分任务未能在超时时间内取消")

        # 关闭 WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass

        # 清理引用
        self.heartbeat_task = None
        self.receive_task = None
        self.reconnect_task = None
        self.ws = None

        # 清理回调函数
        self.on_danmaku = None
        self.on_gift = None
        self.on_superchat = None
        self.on_guard = None
        self.on_interact = None
        self.on_online = None
        self.on_disconnect = None

        # 关闭HTTP客户端
        if self.http_client:
            try:
                await self.http_client.aclose()
            except:
                pass
            self.http_client = None

        print("已断开连接")
    
    async def _get_real_room_id(self):
        """获取真实房间号（短号转长号）"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://live.bilibili.com/",
            }
            # 使用连接池
            response = await self.http_client.get(
                self.ROOM_INFO_URL,
                params={"room_id": self.room_id},
                headers=headers
            )
            print(f"获取真实房间号响应: {response.status_code}, 内容长度: {len(response.text)}")
            data = response.json()
            
            if data.get("code") == 0:
                self.real_room_id = data["data"]["room_id"]
                print(f"真实房间号: {self.real_room_id}")
            else:
                print(f"获取真实房间号失败: code={data.get('code')}, message={data.get('message')}")
        except json.JSONDecodeError as e:
            print(f"获取真实房间号失败: JSON解析错误 - {e}")
            print(f"响应内容: {response.text[:200]}")
        except Exception as e:
            print(f"获取真实房间号失败: {e}")
    
    async def _get_danmu_info(self) -> Dict:
        """获取弹幕服务器信息"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://live.bilibili.com/",
            }

            # 使用旧端点，参数名为 room_id
            params = {"room_id": self.real_room_id}
            print(f"获取弹幕信息，房间号: {self.real_room_id}")

            # 使用连接池
            response = await self.http_client.get(
                self.DANMU_INFO_URL,
                params=params,
                headers=headers
            )
            print(f"获取弹幕信息响应: {response.status_code}, 内容长度: {len(response.text)}")

            # 尝试解析 JSON
            try:
                data = response.json()
            except Exception as json_error:
                print(f"JSON 解析失败: {json_error}")
                print(f"响应内容: {response.text[:200]}")
                return {}

            if data.get("code") == 0:
                response_data = data["data"]

                # 转换为统一的格式
                # 旧端点返回: {token, host, port, host_server_list, server_list, ...}
                # 需要转换为: {token, host_list: [{host, port, wss_port, ws_port}]}

                result = {
                    "token": response_data.get("token", ""),
                    "host_list": response_data.get("host_server_list", [])
                }

                print(f"成功获取弹幕信息: token={result['token'][:20] if result['token'] else 'None'}...")
                return result
            else:
                code = data.get("code")
                message = data.get("message")
                print(f"获取弹幕信息失败: code={code}, message={message}")
                return {}
        except json.JSONDecodeError as e:
            print(f"获取弹幕服务器信息失败: JSON解析错误 - {e}")
            print(f"响应内容: {response.text[:200]}")
            return {}
        except Exception as e:
            print(f"获取弹幕服务器信息失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    async def _send_auth(self, token: str = ""):
        """发送认证包"""
        # 从 Cookie 中获取用户 ID
        uid = 0
        if self.cookies and "DedeUserID" in self.cookies:
            try:
                uid = int(self.cookies["DedeUserID"])
            except:
                pass

        auth_data = {
            "uid": uid,
            "roomid": self.real_room_id,
            "protover": 3,  # 协议版本 3 支持 Brotli 压缩
            "platform": "web",
            "type": 2,
            "key": token
        }

        print(f"认证数据: uid={uid}, roomid={self.real_room_id}, token={'有' if token else '无'}")
        await self._send_packet(Operation.AUTH, json.dumps(auth_data))
        print("认证包已发送")
    
    async def _send_packet(self, operation: int, body: str = ""):
        """发送数据包"""
        body_bytes = body.encode('utf-8')
        header = PacketHeader(
            packet_length=len(body_bytes) + 16,
            header_length=16,
            protocol_version=1,
            operation=operation,
            sequence_id=1
        )
        
        packet = header.to_bytes() + body_bytes
        await self.ws.send(packet)
    
    async def _heartbeat_loop(self):
        """心跳循环（30秒间隔）"""
        try:
            while self.running:
                await self._send_packet(Operation.HEARTBEAT, "[object Object]")
                # 使用更短的睡眠间隔以便更快响应取消
                for _ in range(30):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"心跳循环错误: {e}")
    
    async def _receive_loop(self):
        """消息接收循环"""
        try:
            while self.running:
                try:
                    data = await self.ws.recv()
                    # 将接收到的数据追加到缓冲区
                    self.buffer.extend(data)

                    # 处理缓冲区中的数据
                    await self._handle_packet(self.buffer)
                except websockets.exceptions.ConnectionClosed as e:
                    if self.running:  # 只有在应该运行时才打印错误
                        print(f"WebSocket 连接已关闭: code={e.code}, reason={e.reason}")
                    self.running = False
                    # 如果启用了自动重连，触发重连
                    if self.auto_reconnect and self.running is False:
                        await self._schedule_reconnect()
                    break
                except Exception as e:
                    print(f"接收数据错误: {e}")
                    # 继续运行，不因单个错误而退出

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"接收循环错误: {e}")
            import traceback
            traceback.print_exc()
            self.running = False
        finally:
            # 清理缓冲区
            self.buffer.clear()

    async def _handle_packet(self, buffer):
        """处理数据包"""
        # 确保 buffer 是 bytearray 类型
        if isinstance(buffer, bytes):
            buffer = bytearray(buffer)

        offset = 0
        buffer_len = len(buffer)
        error_count = 0  # 错误计数器
        max_errors = 5  # 减少最大错误次数

        while offset < buffer_len and error_count < max_errors:
            try:
                # 检查是否有足够的数据来读取包头
                if buffer_len - offset < 16:
                    # 数据不足，保留在缓冲区中等待更多数据
                    break

                # 尝试同步到有效的包头
                # B站协议的包头长度通常是16字节，且第一个字段是包的总长度
                # 我们可以通过查找合理的包长度来同步
                sync_found = False
                for sync_offset in range(min(16, buffer_len - offset - 16)):
                    test_offset = offset + sync_offset
                    try:
                        # 尝试解析包头
                        test_header = PacketHeader.from_bytes(bytes(buffer[test_offset:]))
                        
                        # 检查是否是有效的包头
                        if (16 <= test_header.packet_length <= 10000 and
                            test_header.header_length == 16 and
                            0 <= test_header.operation <= 1000):
                            # 找到有效的包头
                            offset = test_offset
                            header = test_header
                            sync_found = True
                            break
                    except:
                        continue
                
                if not sync_found:
                    # 没有找到有效的包头，跳过1字节继续尝试
                    offset += 1
                    error_count += 1
                    continue

                # 检查数据包是否完整
                if buffer_len - offset < header.packet_length:
                    # 数据包不完整，保留在缓冲区中等待更多数据
                    break

                # 提取包体
                body = bytes(buffer[offset + 16:offset + header.packet_length])

                # 根据操作码处理
                if header.operation == Operation.HEARTBEAT_REPLY:
                    # 心跳回复，包含在线人数
                    if len(body) == 4:
                        try:
                            online = struct.unpack('>I', body)[0]
                            print(f"[人气值] 心跳回复在线人数: {online}")
                            if self.on_online:
                                await self.on_online({"online": online, "source": "heartbeat"})
                        except Exception as e:
                            print(f"解析心跳回复错误: {e}")
                            pass

                elif header.operation == Operation.SEND_MSG_REPLY:
                    # 消息推送
                    try:
                        await self._handle_message(body, header.protocol_version)
                    except Exception as e:
                        print(f"处理消息错误: {e}")

                elif header.operation == Operation.AUTH_REPLY:
                    # 认证回复
                    if len(body) > 0:
                        try:
                            auth_reply = json.loads(body.decode('utf-8', errors='ignore'))
                            print(f"认证回复: {auth_reply}")
                        except:
                            print("认证成功（无法解析详细回复）")
                    else:
                        print("认证成功")

                # 成功处理一个包，重置错误计数
                error_count = 0
                offset += header.packet_length

            except Exception as e:
                error_count += 1
                if error_count < 3:
                    print(f"处理数据包错误: {e}")
                # 跳过这个错误的数据包
                if buffer_len - offset >= 1:
                    offset += 1
                else:
                    break

        # 如果错误次数过多，清空缓冲区
        if error_count >= max_errors:
            print("数据包解析错误过多，清空缓冲区")
            buffer.clear()
            offset = 0

        # 删除已处理的数据（仅当是 bytearray 时）
        if offset > 0 and isinstance(buffer, bytearray):
            del buffer[:offset]

    async def _handle_message(self, body: bytes, protocol_version: int):
        """处理消息体"""
        try:
            # 根据协议版本解压
            if protocol_version == 0:
                # 未压缩
                messages = [body]
            elif protocol_version == 2:
                # zlib 压缩
                decompressed = zlib.decompress(body)
                messages = [decompressed]
            elif protocol_version == 3:
                # Brotli 压缩
                try:
                    import brotli
                    decompressed = brotli.decompress(body)
                    messages = [decompressed]
                except ImportError:
                    # 如果没有 brotli，尝试 zlib
                    decompressed = zlib.decompress(body)
                    messages = [decompressed]
            else:
                messages = [body]
            
            # 解析消息
            for msg_data in messages:
                await self._parse_messages(msg_data)
        except Exception as e:
            print(f"处理消息错误: {e}")
    
    async def _parse_messages(self, data: bytes):
        """解析消息（可能包含多条）"""
        offset = 0
        
        while offset < len(data):
            try:
                header = PacketHeader.from_bytes(data[offset:])
                body = data[offset + 16:offset + header.packet_length]
                
                if header.operation == Operation.SEND_MSG_REPLY:
                    try:
                        msg = json.loads(body.decode('utf-8', errors='ignore'))
                        await self._dispatch_message(msg)
                    except json.JSONDecodeError:
                        pass
                
                offset += header.packet_length
            except Exception as e:
                break
    
    async def _dispatch_message(self, msg: dict):
        """分发消息到对应的处理函数"""
        cmd = msg.get("cmd", "")

        # 普通弹幕
        if cmd == "DANMU_MSG":
            await self._handle_danmaku(msg)

        # 礼物
        elif cmd == "SEND_GIFT":
            await self._handle_gift(msg)

        # 醒目留言（SC）
        elif cmd == "SUPER_CHAT_MESSAGE":
            await self._handle_superchat(msg)

        # 上舰
        elif cmd == "GUARD_BUY":
            await self._handle_guard(msg)

        # 用户进入直播间（旧版本，已被INTERACT_WORD_V2替换）
        elif cmd == "INTERACT_WORD":
            await self._handle_interact(msg)
        
        # 用户进入直播间V2（新版本，使用protobuf）
        elif cmd == "INTERACT_WORD_V2":
            await self._handle_interact_v2(msg)

        # 用户关注
        elif cmd == "WATCHED_CHANGE":
            await self._handle_watch(msg)

        # 进入特效（舰长进入）
        elif cmd == "ENTRY_EFFECT":
            await self._handle_entry_effect(msg)

        # 在线人数
        elif cmd == "ONLINE_RANK_COUNT":
            count = msg.get("data", {}).get("count", 0)
            print(f"[人气值] ONLINE_RANK_COUNT在线人数: {count}")
            if self.on_online:
                await self.on_online({"online": count, "source": "rank_count"})
    
    async def _handle_danmaku(self, msg: dict):
        """处理弹幕消息"""
        try:
            info = msg.get("info", [])
            if len(info) < 3:
                return
            
            data = {
                "type": "danmaku",
                "content": info[1],  # 弹幕内容
                "user": {
                    "uid": info[2][0],  # 用户 UID
                    "uname": info[2][1],  # 用户名
                    "is_admin": info[2][2] == 1,  # 是否房管
                    "is_vip": info[2][3] == 1,  # 是否月费老爷
                    "is_svip": info[2][4] == 1,  # 是否年费老爷
                },
                "medal": None,
                "timestamp": info[0][4] if len(info[0]) > 4 else 0
            }
            
            # 粉丝勋章
            if len(info) > 3 and info[3]:
                data["medal"] = {
                    "level": info[3][0],
                    "name": info[3][1],
                    "anchor_uname": info[3][2],
                    "anchor_room_id": info[3][3]
                }
            
            # 检测用户首次出现
            user_uid = data["user"]["uid"]
            user_name = data["user"]["uname"]
            
            if user_uid and user_name and user_uid not in self.user_first_seen:
                # 记录用户首次出现
                import time
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "time": time.time(),
                    "source": "弹幕"
                }
                
                # 触发用户进入事件
                await self._trigger_user_enter(user_name, user_uid, "弹幕")
            
            if self.on_danmaku:
                await self.on_danmaku(data)
        except Exception as e:
            print(f"处理弹幕错误: {e}")
    
    async def _handle_gift(self, msg: dict):
        """处理礼物消息"""
        try:
            data_info = msg.get("data", {})
            
            data = {
                "type": "gift",
                "gift_name": data_info.get("giftName"),
                "gift_id": data_info.get("giftId"),
                "num": data_info.get("num", 1),
                "price": data_info.get("price", 0),  # 单价（金瓜子）
                "coin_type": data_info.get("coin_type", "gold"),
                "total_coin": data_info.get("total_coin", 0),
                "user": {
                    "uid": data_info.get("uid"),
                    "uname": data_info.get("uname"),
                    "face": data_info.get("face")
                },
                "timestamp": data_info.get("timestamp", 0)
            }
            
            # 检测用户首次出现
            user_uid = data["user"]["uid"]
            user_name = data["user"]["uname"]
            
            if user_uid and user_name and user_uid not in self.user_first_seen:
                # 记录用户首次出现
                import time
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "time": time.time(),
                    "source": "礼物"
                }
                
                # 触发用户进入事件
                await self._trigger_user_enter(user_name, user_uid, "送礼")
            
            if self.on_gift:
                await self.on_gift(data)
        except Exception as e:
            print(f"处理礼物错误: {e}")
    
    async def _handle_superchat(self, msg: dict):
        """处理醒目留言（SC）"""
        try:
            data_info = msg.get("data", {})
            
            data = {
                "type": "superchat",
                "content": data_info.get("message"),
                "price": data_info.get("price", 0),
                "user": {
                    "uid": data_info.get("uid"),
                    "uname": data_info.get("user_info", {}).get("uname"),
                    "face": data_info.get("user_info", {}).get("face")
                },
                "start_time": data_info.get("start_time", 0),
                "end_time": data_info.get("end_time", 0),
                "background_color": data_info.get("background_bottom_color", "#EDF5FF")
            }
            
            # 检测用户首次出现
            user_uid = data["user"]["uid"]
            user_name = data["user"]["uname"]
            
            if user_uid and user_name and user_uid not in self.user_first_seen:
                # 记录用户首次出现
                import time
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "time": time.time(),
                    "source": "SC"
                }
                
                # 触发用户进入事件
                await self._trigger_user_enter(user_name, user_uid, "SC")
            
            if self.on_superchat:
                await self.on_superchat(data)
        except Exception as e:
            print(f"处理SC错误: {e}")
    
    async def _handle_guard(self, msg: dict):
        """处理上舰消息"""
        try:
            data_info = msg.get("data", {})
            
            # 舰长类型：1-总督，2-提督，3-舰长
            guard_level = data_info.get("guard_level", 3)
            guard_names = {1: "总督", 2: "提督", 3: "舰长"}
            
            data = {
                "type": "guard",
                "guard_level": guard_level,
                "guard_name": guard_names.get(guard_level, "舰长"),
                "price": data_info.get("price", 0),
                "num": data_info.get("num", 1),
                "user": {
                    "uid": data_info.get("uid"),
                    "uname": data_info.get("username")
                },
                "start_time": data_info.get("start_time", 0)
            }
            
            # 检测用户首次出现
            user_uid = data["user"]["uid"]
            user_name = data["user"]["uname"]
            
            if user_uid and user_name and user_uid not in self.user_first_seen:
                # 记录用户首次出现
                import time
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "time": time.time(),
                    "source": "上舰"
                }
                
                # 触发用户进入事件
                await self._trigger_user_enter(user_name, user_uid, "上舰")
            
            if self.on_guard:
                await self.on_guard(data)
        except Exception as e:
            print(f"处理上舰错误: {e}")
    
    async def _handle_interact(self, msg: dict):
        """处理用户进入直播间（旧版本）"""
        try:
            data_info = msg.get("data", {})
            
            # 打印原始数据用于调试
            print(f"[调试] INTERACT_WORD 原始数据: {data_info}")
            
            # 尝试获取更多用户信息
            uid = data_info.get("uid")
            uname = data_info.get("uname")
            
            # 如果没有用户名，尝试从其他字段获取
            if not uname:
                uname = data_info.get("username") or data_info.get("user_name")
            
            # 检查msg_type
            msg_type = data_info.get("msg_type", 1)
            msg_type_name = "进入" if msg_type == 1 else "关注"
            
            print(f"[调试] 用户{msg_type_name}: uid={uid}, uname={uname}")
            
            data = {
                "type": "interact",
                "msg_type": msg_type,  # 1-进入，2-关注
                "user": {
                    "uid": uid,
                    "uname": uname
                },
                "timestamp": data_info.get("timestamp", 0)
            }
            
            if self.on_interact:
                await self.on_interact(data)
        except Exception as e:
            print(f"处理互动错误: {e}")
    
    async def _handle_interact_v2(self, msg: dict):
        """处理用户进入直播间V2（新版本，使用protobuf）"""
        try:
            data_info = msg.get("data", {})
            
            # 获取protobuf数据
            pb_data = data_info.get("pb", "")
            if not pb_data:
                print("[调试] INTERACT_WORD_V2 缺少 pb 数据")
                return
            
            # 使用新的protobuf解析器
            interact_data = parse_interact_word_v2(pb_data)
            if not interact_data:
                print("[调试] 解析INTERACT_WORD_V2失败")
                return
            
            uid = interact_data.get("uid", 0)
            uname = interact_data.get("uname", "")
            msg_type = interact_data.get("msg_type", 1)
            timestamp = interact_data.get("timestamp", 0)
            
            # 清理用户名
            clean_uname = self._clean_username(uname)
            
            # 检查msg_type
            msg_type_names = {
                1: "进入",
                2: "关注",
                3: "分享",
                4: "特别关注",
                5: "互粉",
                6: "点赞"
            }
            msg_type_name = msg_type_names.get(msg_type, f"未知类型({msg_type})")
            
            print(f"[调试] 用户{msg_type_name}: uid={uid}, uname={clean_uname}")
            
            # 只处理进入事件（msg_type=1）
            if msg_type == 1 and uid and clean_uname:
                # 检测用户首次出现
                if uid not in self.user_first_seen:
                    import time
                    self.user_first_seen[uid] = {
                        "name": clean_uname,
                        "time": time.time(),
                        "source": "进入事件"
                    }
                
                # 触发用户进入事件
                await self._trigger_user_enter(clean_uname, uid, "进入事件")
            
            # 构造数据
            data = {
                "type": "interact",
                "msg_type": msg_type,
                "user": {
                    "uid": uid,
                    "uname": uname
                },
                "timestamp": timestamp,
                "source": "INTERACT_WORD_V2"
            }
            
            if self.on_interact:
                await self.on_interact(data)
                
        except Exception as e:
            print(f"处理互动V2错误: {e}")
    
    
    
    async def _handle_watch(self, msg: dict):
        """处理人气值变化（WATCHED_CHANGE）"""
        try:
            data_info = msg.get("data", {})
            
            # WATCHED_CHANGE是人气值变化通知，不包含具体用户信息
            # 它只包含观看人数等信息，不是用户进入或关注事件
            num = data_info.get("num", 0)
            text_small = data_info.get("text_small", "")
            text_large = data_info.get("text_large", "")
            
            # 这个事件通常每30秒触发一次，用于更新人气值
            # 我们不需要处理它为用户进入事件
            
            # 如果需要，可以更新在线人数显示
            print(f"[人气值] WATCHED_CHANGE人气值: {num}")
            if self.on_online:
                await self.on_online({"online": num, "source": "watched_change"})
                
        except Exception as e:
            print(f"处理人气值变化错误: {e}")
    
    async def _handle_watched_change(self, msg: dict):
        """处理用户关注"""
        try:
            data_info = msg.get("data", {})
            uname = data_info.get("uname", "未知用户")
            print(f"[弹幕调试] 用户关注: {uname}")
            
            data = {
                "type": "follow",
                "user": {
                    "uid": data_info.get("uid"),
                    "uname": uname
                },
                "timestamp": data_info.get("timestamp", 0)
            }
            
            if self.on_interact:
                await self.on_interact(data)
        except Exception as e:
            print(f"处理关注错误: {e}")
    
    async def _handle_entry_effect(self, msg: dict):
        """处理进入特效（舰长进入）"""
        try:
            data_info = msg.get("data", {})
            
            # 打印原始数据用于调试
            print(f"[调试] ENTRY_EFFECT 原始数据: {data_info}")
            
            # 获取用户信息
            uid = data_info.get("uid")
            uname = data_info.get("uname")
            
            # 获取特效信息
            effect_id = data_info.get("effect_id")
            copy_writing = data_info.get("copy_writing")  # 特效文字
            
            print(f"[舰长进入] {uname} (UID: {uid}), 特效: {copy_writing}")
            
            # 构造数据
            data = {
                "type": "entry_effect",
                "user": {
                    "uid": uid,
                    "uname": uname
                },
                "effect": {
                    "id": effect_id,
                    "copy_writing": copy_writing
                },
                "timestamp": data_info.get("timestamp", 0)
            }
            
            # 调用插件的on_interact方法处理
            if hasattr(self, 'plugin_manager'):
                for plugin in self.plugin_manager.plugins.values():
                    if plugin.enabled and hasattr(plugin, 'on_interact'):
                        try:
                            await plugin.on_interact(data)
                        except Exception as e:
                            print(f"插件 {plugin.name} 处理进入特效事件失败: {e}")
            
        except Exception as e:
            print(f"处理进入特效错误: {e}")
    
    def _clean_username(self, username: str) -> str:
        """清理用户名，移除控制字符和URL"""
        if not username:
            return username
        
        # 移除换行符和其他控制字符
        cleaned = ''.join(char for char in username if ord(char) >= 32 or char in '\t\n\r')
        
        # 移除B站头像URL - 改进的逻辑
        if 'http' in cleaned and 'bfs/face/' in cleaned:
            # 查找URL的开始
            http_start = cleaned.find('http')
            if http_start != -1:
                # 查找URL的结束 - 尝试多种图片格式
                url_end = -1
                for ext in ['.jpg', '.png', '.jpeg', '.gif', '.webp']:
                    ext_end = cleaned.find(ext, http_start)
                    if ext_end != -1:
                        url_end = ext_end + len(ext)
                        break
                
                if url_end != -1:
                    # 找到图片扩展名，移除整个URL
                    before_url = cleaned[:http_start].rstrip()
                    after_url = cleaned[url_end:].lstrip()
                    cleaned = before_url + ' ' + after_url if after_url else before_url
                else:
                    # 没找到图片扩展名，尝试找到下一个空格或特殊字符
                    space_end = cleaned.find(' ', http_start)
                    if space_end != -1:
                        cleaned = cleaned[:http_start].rstrip() + cleaned[space_end:]
                    else:
                        # 如果没有空格，直接移除从http开始的所有内容
                        cleaned = cleaned[:http_start].rstrip()
        
        # 清理多余的空格
        cleaned = ' '.join(cleaned.split())
        
        # 去除首尾空格
        cleaned = cleaned.strip()
        
        # 限制长度（在去除空格后）
        if len(cleaned) > 20:
            cleaned = cleaned[:20].rstrip()
        
        # 如果清理后为空或只有空格，返回默认值
        if not cleaned or cleaned.isspace():
            return "用户"
        
        return cleaned
    
    async def _trigger_user_enter(self, user_name: str, user_uid: int, source: str):
        """触发用户进入事件"""
        # 清理用户名
        clean_name = self._clean_username(user_name)
        
        # 避免重复触发
        key = f"{user_uid}:{clean_name}"
        if key in self.user_enter_history:
            return
        
        self.user_enter_history.add(key)
        
        # 构造进入事件数据
        import time
        enter_data = {
            "type": "interact",
            "msg_type": 1,  # 1-进入
            "user": {
                "uid": user_uid,
                "uname": clean_name
            },
            "timestamp": time.time(),
            "source": source  # 进入来源：弹幕、送礼、SC、上舰等
        }
        
        print(f"[用户进入] {clean_name} (UID: {user_uid}) - 来源: {source}")
        
        # 调用插件的on_interact方法
        if hasattr(self, 'plugin_manager'):
            for plugin in self.plugin_manager.plugins.values():
                if plugin.enabled and hasattr(plugin, 'on_interact'):
                    try:
                        await plugin.on_interact(enter_data)
                    except Exception as e:
                        print(f"插件 {plugin.name} 处理用户进入事件失败: {e}")
    
    def get_user_stats(self) -> Dict:
        """获取用户统计信息"""
        import time
        current_time = time.time()

        # 统计最近1小时进入的用户
        recent_users = []
        for uid, info in self.user_first_seen.items():
            if current_time - info["time"] < 3600:  # 1小时内
                recent_users.append({
                    "uid": uid,
                    "name": info["name"],
                    "first_seen": info["time"],
                    "source": info["source"]
                })

        return {
            "total_users": len(self.user_first_seen),
            "recent_users": len(recent_users),
            "enter_history_size": len(self.user_enter_history),
            "recent_user_list": recent_users
        }

    async def _schedule_reconnect(self):
        """调度重连任务"""
        # 取消已存在的重连任务
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()

        # 创建新的重连任务
        self.reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """自动重连循环"""
        if not self.auto_reconnect:
            return

        print("开始自动重连流程...")
        self.reconnect_attempts = 0

        while self.reconnect_attempts < self.max_reconnect_attempts and not self.running:
            try:
                self.reconnect_attempts += 1
                wait_time = min(2 ** self.reconnect_attempts, 60)  # 指数退避，最多60秒

                print(f"尝试重连 ({self.reconnect_attempts}/{self.max_reconnect_attempts}), {wait_time}秒后开始...")

                # 等待退避时间
                await asyncio.sleep(wait_time)

                # 清理旧资源
                if self.ws:
                    try:
                        await self.ws.close()
                    except:
                        pass
                    self.ws = None

                # 尝试重新连接
                success = await self.connect()

                if success:
                    print("自动重连成功！")
                    self.reconnect_attempts = 0  # 重置重连计数
                    return
                else:
                    print(f"重连尝试 {self.reconnect_attempts} 失败")

            except Exception as e:
                print(f"重连过程出错: {e}")
                import traceback
                traceback.print_exc()

        # 如果所有重连尝试都失败了
        if not self.running:
            print("已达到最大重连次数，停止自动重连")
            # 调用断开连接回调
            if self.on_disconnect:
                try:
                    await self.on_disconnect({"reason": "max_reconnect_attempts_reached"})
                except Exception as e:
                    print(f"调用断开连接回调失败: {e}")
