# -*- coding: utf-8 -*-
"""
礼物自动感谢插件
自动感谢送礼物的用户，支持不同价值的礼物使用不同的感谢语
"""

import time
import random
from typing import Optional, Dict, List
from collections import defaultdict
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase
from core.plugin_base import PluginBaseEnhanced
from core.danmaku_sender import get_danmaku_sender


class AutoThanksPlugin(PluginBaseEnhanced):
    """礼物自动感谢插件"""
    
    name = "自动感谢"
    description = "自动感谢送礼物的用户，支持不同价值的礼物使用不同的感谢语"
    version = "1.0.0"
    author = "BililiveRobot"
    
    config_schema = [
        {
            "key": "enable_gift_thanks",
            "label": "启用礼物感谢",
            "type": "boolean",
            "default": True
        },
        {
            "key": "enable_sc_thanks",
            "label": "启用SC感谢",
            "type": "boolean",
            "default": True
        },
        {
            "key": "enable_guard_thanks",
            "label": "启用上舰感谢",
            "type": "boolean",
            "default": True
        },
        {
            "key": "min_gift_value",
            "label": "最小感谢礼物价值（金瓜子）",
            "type": "number",
            "default": 100,
            "min": 0,
            "max": 10000
        },
        {
            "key": "thanks_interval",
            "label": "感谢间隔（秒）",
            "type": "number",
            "default": 5,
            "min": 1,
            "max": 30
        },
        {
            "key": "max_thanks_per_minute",
            "label": "每分钟最大感谢次数",
            "type": "number",
            "default": 10,
            "min": 1,
            "max": 30
        },
        {
            "key": "gift_thank_messages",
            "label": "礼物感谢语列表",
            "type": "array",
            "default": [
                "感谢 {user} 的 {gift_name}！",
                "谢谢 {user} 送的 {gift_name}~",
                "{user} 的 {gift_name} 收到了，感谢！",
                "感谢 {user} 的 {gift_name}，支持了！",
                "收到 {user} 的 {gift_name}，谢谢老板！",
                "感谢 {user} 送来的价值 {value} 元的 {gift_name}！",
                "感谢 {user} 送的 {gift_name}，价值 {value} 元，谢谢老板！"
            ]
        },
        {
            "key": "sc_thank_messages",
            "label": "SC感谢语列表",
            "type": "array",
            "default": [
                "感谢 {user} 的SC！",
                "谢谢 {user} 的醒目留言！",
                "{user} 的SC收到了，感谢支持！",
                "感谢 {user} 的SC，太感动了！",
                "收到 {user} 的SC，谢谢老板！"
            ]
        },
        {
            "key": "guard_thank_messages",
            "label": "上舰感谢语列表",
            "type": "array",
            "default": [
                "感谢 {user} 上{guard_name}！",
                "欢迎 {user} 成为{guard_name}！",
                "{user} 上{guard_name}了，感谢支持！",
                "感谢 {user} 的{guard_name}，太棒了！",
                "恭喜 {user} 成为{guard_name}！"
            ]
        },
        {
            "key": "vip_thank_messages",
            "label": "VIP礼物感谢语列表",
            "type": "array",
            "default": [
                "感谢 {user} 的 {gift_name}！老板大气！",
                "哇！{user} 送的 {gift_name}，太感谢了！",
                "{user} 老板太给力了，感谢 {gift_name}！",
                "收到 {user} 的 {gift_name}，老板威武！",
                "感谢 {user} 的 {gift_name}，老板666！"
            ]
        },
        {
            "key": "batch_thanks_threshold",
            "label": "批量感谢阈值",
            "type": "number",
            "default": 5,
            "min": 2,
            "max": 20
        },
        {
            "key": "batch_thanks_message",
            "label": "批量感谢消息模板",
            "type": "string",
            "default": "感谢 {users} 等人的礼物！"
        },
        {
            "key": "enable_cumulative_thanks",
            "label": "启用累计感谢",
            "type": "boolean",
            "default": True
        },
        {
            "key": "cumulative_thresholds",
            "label": "累计感谢阈值（JSON格式）",
            "type": "string",
            "default": '{"1000": "感谢 {user} 累计送了 {total_value} 金瓜子！", "5000": "哇！{user} 累计送了 {total_value} 金瓜子，太感谢了！", "10000": "{user} 老板累计送了 {total_value} 金瓜子，感谢支持！"}'
        }
    ]
    
    def __init__(self):
        super().__init__()
        
        # 感谢历史
        self.thanks_history = []  # 感谢记录
        self.last_thanks_time = 0
        
        # 用户累计送礼统计
        self.user_cumulative = defaultdict(int)  # 用户 -> 累计价值
        
        # 批量感谢缓存
        self.batch_thanks_buffer = []  # 待感谢的用户列表
        
        # 感谢时间队列（用于控制频率）
        self.thanks_times = []
        
        # 累计感谢阈值
        self.cumulative_thresholds = {}
        self._parse_cumulative_thresholds()
    
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """处理弹幕事件（自动感谢插件不需要处理弹幕）"""
        return data
    
    async def on_gift(self, data: dict) -> Optional[dict]:
        """处理礼物事件"""
        if not self.config.get("enable_gift_thanks", True):
            return data
        
        user_info = data.get("user", {})
        user_name = user_info.get("uname", "")
        gift_name = data.get("gift_name", "")
        gift_id = data.get("gift_id", 0)
        num = data.get("num", 1)
        total_coin = data.get("total_coin", 0)
        
        if not user_name or not gift_name:
            return data
        
        # 检查最小感谢价值
        min_value = self.config.get("min_gift_value", 100)
        if total_coin < min_value:
            return data
        
        current_time = time.time()
        
        # 更新累计统计
        self.user_cumulative[user_name] += total_coin
        
        # 检查累计感谢
        if self.config.get("enable_cumulative_thanks", True):
            await self._check_cumulative_thanks(user_name, current_time)
        
        # 检查感谢频率
        if not self._check_thanks_frequency(current_time):
            # 加入批量感谢缓冲
            self._add_to_batch_buffer(user_name, "gift", total_coin)
            return data
        
        # 生成感谢语
        thank_message = self._get_gift_thank_message(user_name, gift_name, total_coin, num)
        
        if thank_message:
            # 发送感谢
            await self._send_thanks(thank_message)
            
            # 记录感谢历史
            self._record_thanks(user_name, "gift", thank_message, total_coin, current_time)
        
        return data
    
    async def on_superchat(self, data: dict) -> Optional[dict]:
        """处理SC事件"""
        if not self.config.get("enable_sc_thanks", True):
            return data
        
        user_info = data.get("user", {})
        user_name = user_info.get("uname", "")
        price = data.get("price", 0)
        content = data.get("content", "")
        
        if not user_name:
            return data
        
        current_time = time.time()
        
        # 更新累计统计（SC价值转换为金瓜子）
        self.user_cumulative[user_name] += price * 1000
        
        # 检查感谢频率
        if not self._check_thanks_frequency(current_time):
            # 加入批量感谢缓冲
            self._add_to_batch_buffer(user_name, "sc", price * 1000)
            return data
        
        # 生成感谢语
        thank_message = self._get_sc_thank_message(user_name, price, content)
        
        if thank_message:
            # 发送感谢
            await self._send_thanks(thank_message)
            
            # 记录感谢历史
            self._record_thanks(user_name, "sc", thank_message, price * 1000, current_time)
        
        return data
    
    async def on_guard(self, data: dict) -> Optional[dict]:
        """处理上舰事件"""
        if not self.config.get("enable_guard_thanks", True):
            return data
        
        user_info = data.get("user", {})
        user_name = user_info.get("uname", "")
        guard_level = data.get("guard_level", 3)
        guard_name = data.get("guard_name", "舰长")
        price = data.get("price", 0)
        
        if not user_name:
            return data
        
        current_time = time.time()
        
        # 更新累计统计
        self.user_cumulative[user_name] += price
        
        # 检查感谢频率
        if not self._check_thanks_frequency(current_time):
            # 加入批量感谢缓冲
            self._add_to_batch_buffer(user_name, "guard", price)
            return data
        
        # 生成感谢语
        thank_message = self._get_guard_thank_message(user_name, guard_name, guard_level)
        
        if thank_message:
            # 发送感谢
            await self._send_thanks(thank_message)
            
            # 记录感谢历史
            self._record_thanks(user_name, "guard", thank_message, price, current_time)
        
        return data
    
    def _check_thanks_frequency(self, current_time: float) -> bool:
        """检查感谢频率"""
        # 检查感谢间隔
        if current_time - self.last_thanks_time < self.config.get("thanks_interval", 5):
            return False
        
        # 清理1分钟前的记录
        self.thanks_times = [t for t in self.thanks_times if current_time - t < 60]
        
        # 检查是否超过限制
        max_per_minute = self.config.get("max_thanks_per_minute", 10)
        
        return len(self.thanks_times) < max_per_minute
    
    def _get_gift_thank_message(self, user_name: str, gift_name: str, total_coin: int, num: int) -> str:
        """获取礼物感谢语"""
        # 判断是否VIP礼物（价值较高）
        is_vip = total_coin >= 1000  # 1000金瓜子以上认为是VIP礼物

        if is_vip:
            messages_config = self.config.get("vip_thank_messages", [])
        else:
            messages_config = self.config.get("gift_thank_messages", [])

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
        message = message.replace("{user}", user_name)
        message = message.replace("{gift_name}", gift_name)
        message = message.replace("{num}", str(num))

        # 计算价值（金瓜子转换为元，支持小数点）
        # 1000金瓜子 = 1元
        value_yuan = total_coin / 1000.0

        # 替换价值占位符
        # {value} 替换为金瓜子数（整数）
        message = message.replace("{value}", str(total_coin))
        # {value_yuan} 替换为元数（保留2位小数）
        message = message.replace("{value_yuan}", f"{value_yuan:.2f}")

        return message
    
    def _get_sc_thank_message(self, user_name: str, price: float, content: str) -> str:
        """获取SC感谢语"""
        messages_config = self.config.get("sc_thank_messages", [])
        
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
        message = message.replace("{user}", user_name)
        message = message.replace("{price}", str(price))
        message = message.replace("{content}", content[:20] + "..." if len(content) > 20 else content)
        
        return message
    
    def _get_guard_thank_message(self, user_name: str, guard_name: str, guard_level: int) -> str:
        """获取上舰感谢语"""
        messages_config = self.config.get("guard_thank_messages", [])
        
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
        message = message.replace("{user}", user_name)
        message = message.replace("{guard_name}", guard_name)
        message = message.replace("{guard_level}", str(guard_level))
        
        return message
    
    async def _send_thanks(self, message: str):
        """发送感谢"""
        sender = get_danmaku_sender()
        if sender:
            result = await sender.send(message)
            if result.get("success"):
                print(f"感谢已发送: {message}")
                self.last_thanks_time = time.time()
                self.thanks_times.append(self.last_thanks_time)
            else:
                print(f"感谢发送失败: {result.get('message')}")
    
    def _record_thanks(self, user_name: str, thanks_type: str, message: str, value: int, current_time: float):
        """记录感谢历史"""
        self.thanks_history.append({
            "user": user_name,
            "type": thanks_type,
            "message": message,
            "value": value,
            "time": current_time
        })
        
        # 保留最近200条记录
        if len(self.thanks_history) > 200:
            self.thanks_history = self.thanks_history[-200:]
    
    def _add_to_batch_buffer(self, user_name: str, thanks_type: str, value: int):
        """添加到批量感谢缓冲"""
        self.batch_thanks_buffer.append({
            "user": user_name,
            "type": thanks_type,
            "value": value,
            "time": time.time()
        })
        
        # 检查是否需要发送批量感谢
        threshold = self.config.get("batch_thanks_threshold", 5)
        
        if len(self.batch_thanks_buffer) >= threshold:
            self._send_batch_thanks()
    
    def _send_batch_thanks(self):
        """发送批量感谢"""
        if not self.batch_thanks_buffer:
            return
        
        # 获取最近的用户列表
        recent_users = [item["user"] for item in self.batch_thanks_buffer[-5:]]
        unique_users = list(set(recent_users))
        
        if len(unique_users) >= 3:
            # 构建批量感谢消息
            template = self.config.get("batch_thanks_message", "感谢 {users} 等人的礼物！")
            
            if len(unique_users) <= 3:
                users_str = "、".join(unique_users)
            else:
                users_str = "、".join(unique_users[:3]) + "等"
            
            message = template.replace("{users}", users_str)
            
            # 发送批量感谢
            asyncio.create_task(self._send_thanks(message))
            
            # 清空缓冲
            self.batch_thanks_buffer.clear()
    
    def _parse_cumulative_thresholds(self):
        """解析累计感谢阈值"""
        try:
            thresholds_str = self.config.get("cumulative_thresholds", "{}")
            self.cumulative_thresholds = json.loads(thresholds_str)
        except:
            self.cumulative_thresholds = {}
    
    async def _check_cumulative_thanks(self, user_name: str, current_time: float):
        """检查累计感谢"""
        cumulative_value = self.user_cumulative[user_name]
        
        # 检查是否达到某个阈值
        for threshold_value in sorted(self.cumulative_thresholds.keys(), key=int):
            if cumulative_value >= int(threshold_value):
                # 检查是否已经感谢过这个阈值
                last_threshold = self.user_cumulative.get(f"{user_name}_last_threshold", 0)
                
                if int(threshold_value) > last_threshold:
                    # 发送累计感谢
                    template = self.cumulative_thresholds[threshold_value]
                    message = template.replace("{user}", user_name)
                    message = message.replace("{total_value}", str(cumulative_value))
                    
                    await self._send_thanks(message)
                    
                    # 更新最后感谢的阈值
                    self.user_cumulative[f"{user_name}_last_threshold"] = int(threshold_value)
                    
                    # 记录感谢历史
                    self._record_thanks(user_name, "cumulative", message, cumulative_value, current_time)
    
    def update_config(self, new_config: Dict):
        """更新配置时重新解析累计阈值"""
        super().update_config(new_config)
        self._parse_cumulative_thresholds()
    
    def get_thanks_stats(self) -> Dict:
        """获取感谢统计"""
        current_time = time.time()
        
        # 统计最近1小时的数据
        recent_thanks = [
            t for t in self.thanks_history
            if current_time - t["time"] < 3600
        ]
        
        # 按类型统计
        type_stats = defaultdict(int)
        value_stats = defaultdict(int)
        
        for thanks in recent_thanks:
            type_stats[thanks["type"]] += 1
            value_stats[thanks["type"]] += thanks["value"]
        
        # 统计感谢的用户
        thanked_users = set(t["user"] for t in recent_thanks)
        
        # 累计送礼排行
        top_gifters = sorted(
            self.user_cumulative.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_thanks": len(self.thanks_history),
            "recent_thanks": len(recent_thanks),
            "thanked_users": len(thanked_users),
            "type_stats": dict(type_stats),
            "value_stats": dict(value_stats),
            "top_gifters": [{"user": user, "value": value} for user, value in top_gifters],
            "batch_buffer_size": len(self.batch_thanks_buffer)
        }
    
    def reset_history(self):
        """重置感谢历史"""
        self.thanks_history.clear()
        self.batch_thanks_buffer.clear()
        self.thanks_times.clear()
        self.last_thanks_time = 0
        print("感谢历史已重置")
    
    def reset_cumulative(self):
        """重置累计统计"""
        self.user_cumulative.clear()
        print("累计统计已重置")