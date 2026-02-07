# -*- coding: utf-8 -*-
"""
自动欢迎语插件
检测用户进入直播间，自动发送欢迎语
"""

import time
import random
import json
from typing import Optional, Dict, List
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase
from core.plugin_base import PluginBaseEnhanced
from core.danmaku_sender import get_danmaku_sender


class AutoWelcomePlugin(PluginBaseEnhanced):
    """自动欢迎语插件"""
    
    name = "自动欢迎语"
    description = "检测用户进入直播间，自动发送欢迎语"
    version = "1.0.0"
    author = "BililiveRobot"
    
    config_schema = [
        {
            "key": "enable_welcome",
            "label": "启用自动欢迎",
            "type": "boolean",
            "default": True
        },
        {
            "key": "welcome_messages",
            "label": "欢迎语列表",
            "type": "array",
            "default": [
                "欢迎 {user} 来到直播间！",
                "哇，{user} 来了！欢迎欢迎~",
                "{user} 进来了，一起看直播吧！",
                "欢迎新朋友 {user}！",
                "Hi {user}，欢迎来到直播间~"
            ]
        },
        {
            "key": "welcome_vip_messages",
            "label": "VIP欢迎语列表",
            "type": "array",
            "default": [
                "欢迎 {user} 老板来到直播间！",
                "哇！{user} 大佬来了！",
                "欢迎 {user} 回来！",
                "{user} 老板好！欢迎欢迎~"
            ]
        },
        {
            "key": "welcome_interval",
            "label": "欢迎间隔（秒）",
            "type": "number",
            "default": 30,
            "min": 10,
            "max": 300
        },
        {
            "key": "max_welcome_per_minute",
            "label": "每分钟最大欢迎次数",
            "type": "number",
            "default": 3,
            "min": 1,
            "max": 10
        },
        {
            "key": "welcome_new_only",
            "label": "只欢迎新用户",
            "type": "boolean",
            "default": True
        },
        {
            "key": "ignore_users",
            "label": "忽略用户列表（逗号分隔）",
            "type": "string",
            "default": ""
        },
        {
            "key": "enable_follow_welcome",
            "label": "启用关注欢迎",
            "type": "boolean",
            "default": True
        },
        {
            "key": "follow_messages",
            "label": "关注欢迎语列表",
            "type": "array",
            "default": [
                "感谢 {user} 的关注！",
                "{user} 关注了，感谢支持！",
                "欢迎新关注 {user}！",
                "谢谢 {user} 的关注！"
            ]
        }
    ]
    
    def __init__(self):
        super().__init__()
        
        # 用户欢迎历史
        self.welcome_history = []  # 已欢迎的用户列表
        self.follow_history = {}   # 用户名 -> 上次关注时间
        self.user_last_welcome = {}  # 每个用户最后被欢迎的时间
        
        # 欢迎统计
        self.welcome_stats = {
            "total_welcomes": 0,
            "total_follows": 0,
            "recent_welcomes": [],
            "recent_follows": []
        }
        
        # 欢迎时间队列（用于控制频率）
        self.welcome_times = []
        self.last_global_welcome = 0  # 全局最后欢迎时间
        
        # 忽略用户列表
        self.ignore_users = set()
        self._update_ignore_users()
        
        # 用户发言记录
        self.user_speech_records = {}
        
        # 加载保存的数据
        self._load_data()
    
    def record_user_speech(self, user_name: str):
        """记录用户发言"""
        current_time = time.time()
        if user_name not in self.user_speech_records:
            self.user_speech_records[user_name] = {
                "first_speech": current_time,
                "last_speech": current_time,
                "speech_count": 1
            }
        else:
            self.user_speech_records[user_name]["last_speech"] = current_time
            self.user_speech_records[user_name]["speech_count"] += 1
    
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """
        处理弹幕事件

        注意：此方法仅用于记录用户发言，不会在此处发送欢迎语。
        欢迎语会在 on_interact 方法中处理，当检测到用户首次进入时发送。

        记录用户发言的作用：
        1. 追踪用户活跃度
        2. 为后续的用户分析提供数据
        3. 配合用户进入事件，确保欢迎逻辑的一致性
        """
        if not self.config.get("enable_welcome", True):
            return data

        # 确保data是有效的字典
        if not isinstance(data, dict):
            return data

        # 检查是否为机器人自己的消息
        if self.is_bot_message(data):
            return data

        user_name = data.get("user", {}).get("uname", "")

        if not user_name:
            return data

        # 记录用户发言（仅用于统计和分析，不触发欢迎）
        self.record_user_speech(user_name)

        return data
    
    async def on_interact(self, data: dict) -> Optional[dict]:
        """处理用户进入/关注事件"""
        if not self.config.get("enable_welcome", True):
            return data
        
        # 确保data是有效的字典
        if not isinstance(data, dict):
            return data
        
        # 检查是否是新的用户进入事件（通过弹幕、礼物等触发的）
        source = data.get("source", "")
        msg_type = data.get("msg_type", 1)  # 1-进入，2-关注
        user_info = data.get("user", {})
        user_name = user_info.get("uname", "")
        user_uid = user_info.get("uid")
        
        if not user_name:
            return data
        
        # 检查是否在忽略列表
        if user_name in self.ignore_users:
            return data
        
        current_time = time.time()
        
        if msg_type == 1:
            # 用户进入
            await self._handle_user_enter(user_name, user_uid, current_time, source)
        elif msg_type == 2:
            # 用户关注
            if self.config.get("enable_follow_welcome", True):
                await self._handle_user_follow(user_name, user_uid, current_time)
        
        return data
    
    async def on_watch(self, data: dict) -> Optional[dict]:
        """处理用户关注事件（WATCHED_CHANGE）"""
        if not self.config.get("enable_welcome", True):
            return data
        
        if not self.config.get("enable_follow_welcome", True):
            return data
        
        # 确保data是有效的字典
        if not isinstance(data, dict):
            return data
        
        watch_data = data.get("data", {})
        user_name = watch_data.get("uname", "")
        
        if not user_name:
            return data
        
        # 检查是否在忽略列表
        if user_name in self.ignore_users:
            return data
        
        current_time = time.time()
        await self._handle_user_follow(user_name, 0, current_time)
        
        return data
    
    async def _handle_user_enter(self, user_name: str, user_uid: int, current_time: float, source: str = "进入"):
        """处理用户进入"""
        # 检查用户名是否有效
        if not user_name or len(user_name.strip()) == 0:
            print(f"[自动欢迎] 无效用户名: {repr(user_name)}")
            return
        
        # 检查全局欢迎间隔（避免发送过于频繁）
        if current_time - self.last_global_welcome < 5:  # 5秒间隔
            return

        # 检查该用户是否在最近被欢迎过
        user_last_welcome = self.user_last_welcome.get(user_name, 0)
        welcome_interval = self.config.get("welcome_interval", 60)

        # 如果用户最近已被欢迎过，不再发送
        if user_last_welcome > 0 and (current_time - user_last_welcome < welcome_interval):
            return

        # 根据来源选择不同的欢迎策略
        if source == "弹幕":
            # 通过弹幕首次发言，使用普通欢迎语
            message = self._get_welcome_message(user_name)
        elif source == "礼物":
            # 通过送礼首次出现，使用感谢式欢迎语
            message = f"感谢 {user_name} 的礼物，欢迎来到直播间！"
        elif source == "SC":
            # 通过SC首次出现，使用感谢式欢迎语
            message = f"感谢 {user_name} 的SC，欢迎来到直播间！"
        elif source == "上舰":
            # 通过上舰首次出现，使用欢迎语
            message = f"感谢 {user_name} 上舰，欢迎来到直播间！"
        else:
            # 其他情况，使用普通欢迎语
            message = self._get_welcome_message(user_name)
        
        # 如果没有获取到欢迎语，使用默认的简单欢迎语
        if not message:
            message = f"欢迎 {user_name}"

        # 确保消息有效且不为空
        if not message or len(message.strip()) == 0:
            print(f"[自动欢迎] 生成的欢迎语无效: {repr(message)}")
            return

        # 验证消息长度和内容
        if len(message) < 3:
            print(f"[自动欢迎] 欢迎语过短，可能是错误: {repr(message)}")
            # 使用默认欢迎语
            message = f"欢迎 {user_name}"
        
        # 确保消息不包含控制字符
        import re
        if re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', message):
            print(f"[自动欢迎] 欢迎语包含控制字符，已过滤")
            message = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', message)
            if len(message) < 3:
                message = f"欢迎 {user_name}"

        print(f"[自动欢迎] 准备发送欢迎语: {repr(message)}")

        # 发送欢迎语
        await self._send_welcome(message)

        # 记录欢迎历史
        if isinstance(self.welcome_history, list):
            if user_name not in self.welcome_history:
                self.welcome_history.append(user_name)
        self.welcome_times.append(current_time)
        self.user_last_welcome[user_name] = current_time
        self.last_global_welcome = current_time

        # 更新统计
        self.welcome_stats["total_welcomes"] += 1
        self.welcome_stats["recent_welcomes"].append({
            "user": user_name,
            "message": message,
            "time": current_time
        })

        # 保留最近50条记录
        if len(self.welcome_stats["recent_welcomes"]) > 50:
            self.welcome_stats["recent_welcomes"] = self.welcome_stats["recent_welcomes"][-50:]

        # 保存数据
        self._save_data()
    
    async def _handle_user_follow(self, user_name: str, user_uid: int, current_time: float):
        """处理用户关注"""
        # 检查用户名是否有效
        if not user_name or not user_name.strip():
            print(f"[自动欢迎] 无效用户名，跳过关注欢迎: {repr(user_name)}")
            return
        
        # 检查关注间隔
        last_follow = self.follow_history.get(user_name, 0)
        
        if current_time - last_follow < 60:  # 关注间隔1分钟
            return
        
        # 选择关注欢迎语
        follow_message = self._get_follow_message(user_name)
        
        if follow_message:
            print(f"[自动欢迎] 准备发送关注欢迎语: {user_name}")
            # 发送关注欢迎语
            await self._send_welcome(follow_message)
            
            # 更新历史
            self.follow_history[user_name] = current_time
            
            # 更新统计
            self.welcome_stats["total_follows"] += 1
            self.welcome_stats["recent_follows"].append({
                "user": user_name,
                "message": follow_message,
                "time": current_time
            })
            
            # 保留最近50条记录
            if len(self.welcome_stats["recent_follows"]) > 50:
                self.welcome_stats["recent_follows"] = self.welcome_stats["recent_follows"][-50:]
    
    def _check_welcome_frequency(self, current_time: float) -> bool:
        """检查欢迎频率"""
        # 清理1分钟前的记录
        self.welcome_times = [t for t in self.welcome_times if current_time - t < 60]
        
        # 检查是否超过限制
        max_per_minute = self.config.get("max_welcome_per_minute", 3)
        
        return len(self.welcome_times) < max_per_minute
    
    def _get_welcome_message(self, user_name: str) -> str:
        """获取欢迎语"""
        # 获取用户信息（判断是否VIP）
        # 这里可以根据实际情况扩展，比如通过API查询用户信息
        
        # 简单判断：如果用户名包含特殊字符或者长度较长，认为是VIP
        is_vip = self._is_vip_user(user_name)
        
        if is_vip:
            messages_config = self.config.get("welcome_vip_messages", [])
        else:
            messages_config = self.config.get("welcome_messages", [])
        
        # 处理配置格式：可能是字符串（逗号分隔）或数组
        messages = []
        if isinstance(messages_config, str):
            # 如果是字符串，按逗号分割
            if messages_config.strip():
                messages = [msg.strip() for msg in messages_config.split(",")]
        elif isinstance(messages_config, list):
            # 如果是数组，直接使用
            messages = messages_config
        
        if not messages:
            return None
        
        # 随机选择一条
        message = random.choice(messages)
        
        # 替换占位符
        return message.replace("{user}", user_name)
    
    def _get_follow_message(self, user_name: str) -> str:
        """获取关注欢迎语"""
        messages_config = self.config.get("follow_messages", [])
        
        # 处理配置格式：可能是字符串（逗号分隔）或数组
        messages = []
        if isinstance(messages_config, str):
            # 如果是字符串，按逗号分割
            if messages_config.strip():
                messages = [msg.strip() for msg in messages_config.split(",")]
        elif isinstance(messages_config, list):
            # 如果是数组，直接使用
            messages = messages_config
        
        if not messages:
            return None
        
        # 随机选择一条
        message = random.choice(messages)
        
        # 替换占位符
        return message.replace("{user}", user_name)
    
    def _is_vip_user(self, user_name: str) -> bool:
        """判断是否VIP用户（简单实现）"""
        # 这里可以根据实际需求扩展
        # 比如查询用户等级、勋章等
        
        # 简单判断规则
        vip_indicators = ["老板", "大佬", "dalao", "laoban"]
        
        return any(indicator in user_name for indicator in vip_indicators)
    
    async def _send_welcome(self, message: str):
        """发送欢迎语"""
        sender = get_danmaku_sender()
        if sender:
            result = await sender.send(message)
            if not result.get("success"):
                print(f"欢迎语发送失败: {result.get('message')}")
    
    def _update_ignore_users(self):
        """更新忽略用户列表"""
        ignore_str = self.config.get("ignore_users", "")
        if ignore_str:
            self.ignore_users = set(user.strip() for user in ignore_str.split(","))
        else:
            self.ignore_users = set()
    
    def update_config(self, new_config: Dict):
        """更新配置时重载忽略用户列表"""
        super().update_config(new_config)
        self._update_ignore_users()
    
    def get_welcome_stats(self) -> Dict:
        """获取欢迎统计"""
        current_time = time.time()
        
        # 统计最近1小时的数据
        recent_welcomes = [
            w for w in self.welcome_stats["recent_welcomes"]
            if current_time - w["time"] < 3600
        ]
        
        recent_follows = [
            f for f in self.welcome_stats["recent_follows"]
            if current_time - f["time"] < 3600
        ]
        
        # 统计欢迎的用户
        welcomed_users = set(w["user"] for w in recent_welcomes)
        followed_users = set(f["user"] for f in recent_follows)
        
        return {
            "total_welcomes": self.welcome_stats["total_welcomes"],
            "total_follows": self.welcome_stats["total_follows"],
            "recent_welcomes": len(recent_welcomes),
            "recent_follows": len(recent_follows),
            "welcomed_users": len(welcomed_users),
            "followed_users": len(followed_users),
            "welcomed_users_list": list(welcomed_users),
            "followed_users_list": list(followed_users),
            "ignore_users": list(self.ignore_users)
        }
    
    def reset_history(self):
        """重置欢迎历史"""
        self.welcome_history.clear()
        self.follow_history.clear()
        self.welcome_times.clear()
        self.welcome_stats = {
            "total_welcomes": 0,
            "total_follows": 0,
            "recent_welcomes": [],
            "recent_follows": []
        }
        print("欢迎历史已重置")
    
    def add_ignore_user(self, user_name: str):
        """添加忽略用户"""
        self.ignore_users.add(user_name)
        
        # 更新配置
        ignore_str = ",".join(self.ignore_users)
        self.update_config({"ignore_users": ignore_str})
        
        print(f"已添加忽略用户: {user_name}")
    
    def remove_ignore_user(self, user_name: str):
        """移除忽略用户"""
        self.ignore_users.discard(user_name)
        
        # 更新配置
        ignore_str = ",".join(self.ignore_users)
        self.update_config({"ignore_users": ignore_str})
        
        print(f"已移除忽略用户: {user_name}")
    
    def _load_data(self):
        """加载保存的数据"""
        try:
            # 加载欢迎数据
            welcome_file = "./data/welcome_data.json"
            if os.path.exists(welcome_file):
                with open(welcome_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 确保welcome_history是list
                    history = data.get("welcome_history", [])
                    if isinstance(history, dict):
                        # 如果是dict，转换为keys列表
                        self.welcome_history = list(history.keys())
                    else:
                        self.welcome_history = history
                    
                    self.follow_history = data.get("follow_history", {})
                    self.user_last_welcome = data.get("user_last_welcome", {})
                    self.welcome_stats = data.get("welcome_stats", self.welcome_stats)
        except Exception as e:
            print(f"加载欢迎数据失败: {e}")
    
    def _save_data(self):
        """保存数据"""
        try:
            os.makedirs("./data", exist_ok=True)
            
            # 保存欢迎数据
            welcome_file = "./data/welcome_data.json"
            save_data = {
                "welcome_history": self.welcome_history,
                "follow_history": self.follow_history,
                "user_last_welcome": self.user_last_welcome,
                "welcome_stats": self.welcome_stats
            }
            
            with open(welcome_file, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存欢迎数据失败: {e}")