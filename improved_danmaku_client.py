#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
改进的B站直播弹幕客户端
参考 blivedm 库的实现，改进用户进入事件的处理
"""

import asyncio
import json
import time
from typing import Optional, Dict, List, Callable
import httpx

from core.auth import BilibiliAuth


class ImprovedDanmakuClient:
    """改进的弹幕客户端"""
    
    def __init__(self, room_id: int, cookies: Optional[Dict] = None):
        self.room_id = room_id
        self.cookies = cookies or {}
        
        # 回调函数
        self.on_danmaku: Optional[Callable] = None
        self.on_gift: Optional[Callable] = None
        self.on_superchat: Optional[Callable] = None
        self.on_guard: Optional[Callable] = None
        self.on_interact: Optional[Callable] = None
        self.on_online: Optional[Callable] = None
        
        # 用户进入记录
        self.user_enter_history = set()  # 记录已进入的用户，避免重复
        self.user_first_seen = {}  # 记录用户首次出现的时间
        
        # HTTP客户端
        self.http_client = httpx.AsyncClient(cookies=self.cookies)
    
    async def connect(self) -> bool:
        """连接到直播间"""
        try:
            # 获取房间信息
            room_info = await self._get_room_info()
            if not room_info:
                print(f"获取房间信息失败: {self.room_id}")
                return False
            
            # 这里应该实现WebSocket连接
            # 暂时返回True，表示连接成功
            print(f"已连接到直播间: {self.room_id}")
            return True
            
        except Exception as e:
            print(f"连接失败: {e}")
            return False
    
    async def disconnect(self):
        """断开连接"""
        if self.http_client:
            await self.http_client.aclose()
    
    async def _get_room_info(self) -> Optional[Dict]:
        """获取房间信息"""
        try:
            url = f"https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"
            params = {"id": self.room_id}
            
            response = await self.http_client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    return data.get("data")
        except Exception as e:
            print(f"获取房间信息错误: {e}")
        return None
    
    def _handle_danmaku(self, data: Dict):
        """处理弹幕"""
        if self.on_danmaku:
            # 记录用户首次出现
            user_info = data.get("user", {})
            user_name = user_info.get("uname", "")
            user_uid = user_info.get("uid", 0)
            
            if user_name and user_uid and user_uid not in self.user_first_seen:
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "first_seen": time.time(),
                    "type": "danmaku"
                }
                # 触发用户进入事件
                self._trigger_user_enter(user_name, user_uid, "弹幕")
            
            asyncio.create_task(self.on_danmaku(data))
    
    def _handle_gift(self, data: Dict):
        """处理礼物"""
        if self.on_gift:
            user_info = data.get("user", {})
            user_name = user_info.get("uname", "")
            user_uid = user_info.get("uid", 0)
            
            # 记录用户首次出现
            if user_name and user_uid and user_uid not in self.user_first_seen:
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "first_seen": time.time(),
                    "type": "gift"
                }
                # 触发用户进入事件
                self._trigger_user_enter(user_name, user_uid, "送礼")
            
            asyncio.create_task(self.on_gift(data))
    
    def _handle_superchat(self, data: Dict):
        """处理SC"""
        if self.on_superchat:
            user_info = data.get("user", {})
            user_name = user_info.get("uname", "")
            user_uid = user_info.get("uid", 0)
            
            # 记录用户首次出现
            if user_name and user_uid and user_uid not in self.user_first_seen:
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "first_seen": time.time(),
                    "type": "sc"
                }
                # 触发用户进入事件
                self._trigger_user_enter(user_name, user_uid, "SC")
            
            asyncio.create_task(self.on_superchat(data))
    
    def _handle_guard(self, data: Dict):
        """处理上舰"""
        if self.on_guard:
            user_info = data.get("user", {})
            user_name = user_info.get("uname", "")
            user_uid = user_info.get("uid", 0)
            
            # 记录用户首次出现
            if user_name and user_uid and user_uid not in self.user_first_seen:
                self.user_first_seen[user_uid] = {
                    "name": user_name,
                    "first_seen": time.time(),
                    "type": "guard"
                }
                # 触发用户进入事件
                self._trigger_user_enter(user_name, user_uid, "上舰")
            
            asyncio.create_task(self.on_guard(data))
    
    def _handle_interact_word(self, data: Dict):
        """处理互动文字（用户进入/关注）"""
        msg_type = data.get("msg_type", 1)  # 1-进入，2-关注
        user_info = data.get("user", {})
        user_name = user_info.get("uname", "")
        user_uid = user_info.get("uid", 0)
        
        if msg_type == 1 and user_name and user_uid:
            # 用户进入
            self._trigger_user_enter(user_name, user_uid, "进入")
        
        if self.on_interact:
            asyncio.create_task(self.on_interact(data))
    
    def _handle_user_toast(self, data: Dict):
        """处理用户通知（舰长进入）"""
        user_info = data.get("user", {})
        user_name = user_info.get("uname", "")
        user_uid = user_info.get("uid", 0)
        guard_level = data.get("guard_level", 0)
        
        if user_name and user_uid and guard_level > 0:
            # 舰长进入
            self._trigger_user_enter(user_name, user_uid, f"舰长{guard_level}级")
        
        if self.on_guard:
            asyncio.create_task(self.on_guard(data))
    
    def _trigger_user_enter(self, user_name: str, user_uid: int, source: str):
        """触发用户进入事件"""
        # 避免重复触发
        key = f"{user_uid}:{user_name}"
        if key in self.user_enter_history:
            return
        
        self.user_enter_history.add(key)
        
        # 构造进入事件数据
        enter_data = {
            "type": "user_enter",
            "user": {
                "uid": user_uid,
                "uname": user_name
            },
            "source": source,  # 进入来源：弹幕、送礼、SC、上舰、进入等
            "timestamp": time.time()
        }
        
        print(f"[用户进入] {user_name} (UID: {user_uid}) - 来源: {source}")
        
        # 调用回调
        if self.on_interact:
            asyncio.create_task(self.on_interact(enter_data))
    
    def get_user_stats(self) -> Dict:
        """获取用户统计信息"""
        current_time = time.time()
        
        # 统计最近1小时进入的用户
        recent_users = []
        for uid, info in self.user_first_seen.items():
            if current_time - info["first_seen"] < 3600:  # 1小时内
                recent_users.append({
                    "uid": uid,
                    "name": info["name"],
                    "first_seen": info["first_seen"],
                    "type": info["type"]
                })
        
        return {
            "total_users": len(self.user_first_seen),
            "recent_users": len(recent_users),
            "enter_history_size": len(self.user_enter_history),
            "recent_user_list": recent_users
        }


# 使用示例
async def example_usage():
    """使用示例"""
    # 获取认证信息
    auth_manager = BilibiliAuth()
    cookies = auth_manager.get_cookies_dict()
    
    # 创建客户端
    client = ImprovedDanmakuClient(room_id=10055155, cookies=cookies)
    
    # 设置回调
    async def on_danmaku(data):
        print(f"弹幕: {data.get('user', {}).get('uname', '')}: {data.get('content', '')}")
    
    async def on_gift(data):
        print(f"礼物: {data.get('user', {}).get('uname', '')} 送出 {data.get('gift_name', '')}")
    
    async def on_interact(data):
        if data.get("type") == "user_enter":
            print(f"用户进入: {data.get('user', {}).get('uname', '')}")
    
    client.on_danmaku = on_danmaku
    client.on_gift = on_gift
    client.on_interact = on_interact
    
    # 连接
    if await client.connect():
        try:
            # 保持运行
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n停止监听...")
        finally:
            await client.disconnect()
    
    # 打印统计
    stats = client.get_user_stats()
    print(f"\n用户统计: {stats}")


if __name__ == "__main__":
    asyncio.run(example_usage())