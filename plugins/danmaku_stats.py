# -*- coding: utf-8 -*-
"""
弹幕统计插件
实时统计弹幕数量、用户活跃度、礼物价值等
"""

import time
from collections import defaultdict, Counter
from typing import Optional, Dict
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase


class DanmakuStatsPlugin(PluginBase):
    """弹幕统计插件"""
    
    name = "弹幕统计"
    description = "实时统计弹幕数量、用户活跃度、礼物价值等数据"
    version = "1.0.0"
    author = "BililiveRobot"
    
    config_schema = [
        {
            "key": "enable_word_cloud",
            "label": "启用词云统计",
            "type": "boolean",
            "default": True
        },
        {
            "key": "top_users_count",
            "label": "活跃用户排行榜数量",
            "type": "number",
            "default": 10,
            "min": 5,
            "max": 50
        },
        {
            "key": "reset_interval",
            "label": "统计重置间隔（秒）",
            "type": "number",
            "default": 3600,
            "min": 60,
            "max": 86400
        }
    ]
    
    def __init__(self):
        super().__init__()
        
        # 统计数据
        self.stats = {
            "total_danmaku": 0,  # 总弹幕数
            "total_gift": 0,  # 总礼物数
            "total_superchat": 0,  # 总 SC 数
            "total_guard": 0,  # 总上舰数
            "total_gift_value": 0,  # 总礼物价值（金瓜子）
            "total_superchat_value": 0,  # 总 SC 价值（元）
            "total_guard_value": 0,  # 总上舰价值（元）
            "user_danmaku_count": defaultdict(int),  # 用户弹幕数
            "user_gift_value": defaultdict(int),  # 用户送礼价值
            "word_frequency": Counter(),  # 词频统计
            "danmaku_speed": 0,  # 弹幕速度（条/分钟）
            "start_time": time.time(),  # 统计开始时间
            "last_reset_time": time.time()  # 上次重置时间
        }
        
        # 最近一分钟的弹幕时间戳
        self.recent_danmaku_times = []
    
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """处理弹幕事件"""
        # 更新统计
        self.stats["total_danmaku"] += 1
        
        # 用户弹幕数
        user_uid = data.get("user", {}).get("uid")
        if user_uid:
            self.stats["user_danmaku_count"][user_uid] += 1
        
        # 词频统计
        if self.config.get("enable_word_cloud", True):
            content = data.get("content", "")
            words = self._extract_words(content)
            self.stats["word_frequency"].update(words)
        
        # 更新弹幕速度
        current_time = time.time()
        self.recent_danmaku_times.append(current_time)
        
        # 移除一分钟前的记录
        self.recent_danmaku_times = [
            t for t in self.recent_danmaku_times 
            if current_time - t <= 60
        ]
        
        self.stats["danmaku_speed"] = len(self.recent_danmaku_times)
        
        # 检查是否需要重置统计
        self._check_reset()
        
        # 添加统计信息到数据中
        data["stats"] = self.get_stats()
        
        return data
    
    async def on_gift(self, data: dict) -> Optional[dict]:
        """处理礼物事件"""
        self.stats["total_gift"] += data.get("num", 1)
        
        # 计算礼物价值（金瓜子）
        total_coin = data.get("total_coin", 0)
        self.stats["total_gift_value"] += total_coin
        
        # 用户送礼价值
        user_uid = data.get("user", {}).get("uid")
        if user_uid:
            self.stats["user_gift_value"][user_uid] += total_coin
        
        self._check_reset()
        data["stats"] = self.get_stats()
        
        return data
    
    async def on_superchat(self, data: dict) -> Optional[dict]:
        """处理 SC 事件"""
        self.stats["total_superchat"] += 1
        
        # SC 价值（元）
        price = data.get("price", 0)
        self.stats["total_superchat_value"] += price
        
        # 用户送礼价值（转换为金瓜子，1元 = 1000金瓜子）
        user_uid = data.get("user", {}).get("uid")
        if user_uid:
            self.stats["user_gift_value"][user_uid] += price * 1000
        
        self._check_reset()
        data["stats"] = self.get_stats()
        
        return data
    
    async def on_guard(self, data: dict) -> Optional[dict]:
        """处理上舰事件"""
        self.stats["total_guard"] += 1
        
        # 上舰价值（元）
        price = data.get("price", 0) / 1000  # B站返回的是金瓜子
        self.stats["total_guard_value"] += price
        
        # 用户送礼价值
        user_uid = data.get("user", {}).get("uid")
        if user_uid:
            self.stats["user_gift_value"][user_uid] += data.get("price", 0)
        
        self._check_reset()
        data["stats"] = self.get_stats()
        
        return data
    
    def _extract_words(self, text: str) -> list:
        """
        提取文本中的词语（简单实现）
        
        Args:
            text: 文本内容
            
        Returns:
            list: 词语列表
        """
        # 简单的分词（按空格和标点分割）
        import re
        words = re.findall(r'[\w]+', text)
        
        # 过滤长度小于 2 的词
        words = [w for w in words if len(w) >= 2]
        
        return words
    
    def _check_reset(self):
        """检查是否需要重置统计"""
        reset_interval = self.config.get("reset_interval", 3600)
        current_time = time.time()
        
        if current_time - self.stats["last_reset_time"] >= reset_interval:
            self.reset_stats()
    
    def reset_stats(self):
        """重置统计数据"""
        self.stats = {
            "total_danmaku": 0,
            "total_gift": 0,
            "total_superchat": 0,
            "total_guard": 0,
            "total_gift_value": 0,
            "total_superchat_value": 0,
            "total_guard_value": 0,
            "user_danmaku_count": defaultdict(int),
            "user_gift_value": defaultdict(int),
            "word_frequency": Counter(),
            "danmaku_speed": 0,
            "start_time": time.time(),
            "last_reset_time": time.time()
        }
        self.recent_danmaku_times = []
        print("统计数据已重置")
    
    def get_stats(self) -> Dict:
        """获取统计数据"""
        top_users_count = self.config.get("top_users_count", 10)
        
        # 活跃用户排行（按弹幕数）
        top_users = sorted(
            self.stats["user_danmaku_count"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_users_count]
        
        # 土豪排行（按送礼价值）
        top_gifters = sorted(
            self.stats["user_gift_value"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_users_count]
        
        # 热词排行
        top_words = self.stats["word_frequency"].most_common(20)
        
        # 运行时长
        running_time = int(time.time() - self.stats["start_time"])
        
        return {
            "total_danmaku": self.stats["total_danmaku"],
            "total_gift": self.stats["total_gift"],
            "total_superchat": self.stats["total_superchat"],
            "total_guard": self.stats["total_guard"],
            "total_gift_value": self.stats["total_gift_value"],
            "total_superchat_value": self.stats["total_superchat_value"],
            "total_guard_value": self.stats["total_guard_value"],
            "danmaku_speed": self.stats["danmaku_speed"],
            "top_users": [{"uid": uid, "count": count} for uid, count in top_users],
            "top_gifters": [{"uid": uid, "value": value} for uid, value in top_gifters],
            "top_words": [{"word": word, "count": count} for word, count in top_words],
            "running_time": running_time
        }
