# -*- coding: utf-8 -*-
"""
用户对话记录和分析插件
记录所有用户的对话，分析用户行为习惯和兴趣
"""

import time
import json
import re
from typing import Optional, Dict, List, Set
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase
from core.plugin_base import PluginBaseEnhanced
from core.database import db


class UserAnalyticsPlugin(PluginBaseEnhanced):
    """用户对话记录和分析插件"""
    
    name = "用户分析"
    description = "记录所有用户的对话，分析用户行为习惯和兴趣"
    version = "1.0.0"
    author = "BililiveRobot"
    
    config_schema = [
        {
            "key": "enable_record",
            "label": "启用对话记录",
            "type": "boolean",
            "default": True
        },
        {
            "key": "enable_analysis",
            "label": "启用用户分析",
            "type": "boolean",
            "default": True
        },
        {
            "key": "max_messages_per_user",
            "label": "每个用户最大记录消息数",
            "type": "number",
            "default": 1000,
            "min": 100,
            "max": 10000
        },
        {
            "key": "analysis_keywords",
            "label": "分析关键词列表（JSON格式）",
            "type": "string",
            "default": '{"游戏": ["游戏", "玩", "游戏名", "电竞"], "音乐": ["歌", "音乐", "歌曲", "唱"], "美食": ["吃", "美食", "食物", "好吃"], "科技": ["科技", "技术", "编程", "代码"], "生活": ["生活", "日常", "今天", "明天"], "情感": ["喜欢", "爱", "讨厌", "开心", "难过"]}'
        },
        {
            "key": "user_activity_threshold",
            "label": "活跃用户阈值（消息数/天）",
            "type": "number",
            "default": 10,
            "min": 1,
            "max": 100
        }
    ]
    
    def __init__(self):
        super().__init__()

        # 用户数据存储
        self.user_data = {}  # 用户名 -> 用户数据
        self.global_stats = {
            "total_messages": 0,
            "total_users": 0,
            "active_users": [],
            "daily_stats": defaultdict(lambda: {"messages": 0, "users": []})
        }

        # 关键词分析配置
        self.analysis_keywords = {}
        self._parse_keywords()

        # 加载保存的数据（从JSON文件）
        self._load_data()

        # 尝试从数据库同步用户数据
        self._sync_from_database()
    
    def _load_data(self):
        """加载保存的数据"""
        try:
            # 加载用户数据
            user_file = "./data/user_analytics.json"
            if os.path.exists(user_file):
                with open(user_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.user_data = data.get("user_data", {})
                    loaded_stats = data.get("global_stats", {})

                    # 合并全局统计，确保使用list格式
                    self.global_stats["total_messages"] = loaded_stats.get("total_messages", 0)
                    self.global_stats["total_users"] = loaded_stats.get("total_users", 0)

                    # 确保active_users是list
                    active_users = loaded_stats.get("active_users", [])
                    if isinstance(active_users, set):
                        self.global_stats["active_users"] = list(active_users)
                    else:
                        self.global_stats["active_users"] = active_users

                    # 处理daily_stats
                    loaded_daily = loaded_stats.get("daily_stats", {})
                    for date, stats in loaded_daily.items():
                        users = stats.get("users", [])
                        if isinstance(users, set):
                            users = list(users)
                        self.global_stats["daily_stats"][date] = {
                            "messages": stats.get("messages", 0),
                            "users": users
                        }
        except Exception as e:
            print(f"加载用户分析数据失败: {e}")

    def _sync_from_database(self):
        """从数据库同步用户数据"""
        try:
            users = db.get_all_users_analytics(limit=1000)
            for user_data in users:
                user_name = user_data['user_name']
                if user_name not in self.user_data:
                    self.user_data[user_name] = {
                        "messages": [],
                        "danmaku_count": user_data.get('danmaku_count', 0),
                        "gift_count": user_data.get('gift_count', 0),
                        "gift_value": user_data.get('gift_value', 0),
                        "first_seen": user_data.get('first_seen'),
                        "last_seen": user_data.get('last_seen'),
                        "interests": user_data.get('interests', []),
                        "sentiment_score": user_data.get('sentiment_score', 0),
                        "activity_level": user_data.get('activity_level', 'low')
                    }
            print(f"[用户分析] 从数据库同步了 {len(users)} 个用户数据")
        except Exception as e:
            print(f"[用户分析] 从数据库同步数据失败: {e}")

    def _save_to_database(self, user_name: str):
        """保存用户数据到数据库"""
        try:
            if user_name not in self.user_data:
                return

            user_data = self.user_data[user_name]
            db_user_data = {
                'user_name': user_name,
                'danmaku_count': user_data.get('danmaku_count', 0),
                'gift_count': user_data.get('gift_count', 0),
                'gift_value': user_data.get('gift_value', 0),
                'last_seen': user_data.get('last_seen'),
                'first_seen': user_data.get('first_seen'),
                'interests': user_data.get('interests', []),
                'sentiment_score': user_data.get('sentiment_score', 0),
                'activity_level': user_data.get('activity_level', 'low')
            }
            db.save_user_analytics(db_user_data)
        except Exception as e:
            print(f"[用户分析] 保存用户数据到数据库失败: {e}")

    def _save_data(self):
        """保存数据"""
        try:
            os.makedirs("./data", exist_ok=True)

            # 保存用户数据到JSON文件（兼容性）
            user_file = "./data/user_analytics.json"
            save_data = {
                "user_data": self.user_data,
                "global_stats": {
                    "total_messages": self.global_stats["total_messages"],
                    "total_users": self.global_stats["total_users"],
                    "active_users": self.global_stats["active_users"],
                    "daily_stats": self.global_stats["daily_stats"]
                }
            }

            with open(user_file, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)

            # 保存最近活跃的用户数据到数据库
            current_time = time.time()
            recent_users = []
            for user_name, user_data in self.user_data.items():
                last_seen = user_data.get('last_seen', 0)
                if current_time - last_seen < 86400:  # 24小时内的用户
                    recent_users.append(user_name)

            for user_name in recent_users:
                self._save_to_database(user_name)

        except Exception as e:
            print(f"保存用户分析数据失败: {e}")
    
    def _parse_keywords(self):
        """解析分析关键词"""
        try:
            keywords_str = self.config.get("analysis_keywords", "{}")
            self.analysis_keywords = json.loads(keywords_str)
        except Exception as e:
            print(f"解析关键词配置失败: {e}")
    
    async def _on_danmaku_impl(self, data: dict) -> Optional[dict]:
        """处理弹幕事件"""
        if not self.config.get("enable_record", True):
            return data
        
        # 确保data是有效的字典
        if not isinstance(data, dict):
            return data
        
        # 检查是否为机器人自己的消息
        if self.is_bot_message(data):
            return data
        
        content = data.get("content", "").strip()
        user_name = data.get("user", {}).get("uname", "") if "user" in data else ""
        timestamp = data.get("timestamp", time.time())
        
        # 确保时间戳是有效的时间戳（秒）
        try:
            if isinstance(timestamp, (int, float)):
                # 如果是毫秒级时间戳，转换为秒
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
            else:
                timestamp = time.time()
        except:
            timestamp = time.time()
        
        if not user_name or not content:
            return data
        
        # 记录消息
        self._record_message(user_name, content, timestamp)
        
        # 分析用户兴趣
        if self.config.get("enable_analysis", True):
            self._analyze_user_interest(user_name, content)
        
        return data
    
    def _record_message(self, user_name: str, content: str, timestamp: float):
        """记录用户消息"""
        # 获取或创建用户数据
        user_data = self.user_data.get(user_name, {
            "first_seen": timestamp,
            "last_seen": timestamp,
            "message_count": 0,
            "messages": [],
            "interests": {},  # 使用普通dict而不是defaultdict
            "activity_pattern": {},  # 按小时统计
            "word_frequency": {},  # 使用普通dict而不是Counter
            "emotion_scores": [],
            "interaction_users": []  # 使用list而不是set
        })
        
        # 更新用户数据
        user_data["last_seen"] = timestamp
        user_data["message_count"] += 1
        
        # 添加消息记录
        user_data["messages"].append({
            "content": content,
            "timestamp": timestamp
        })
        
        # 限制消息数量
        max_messages = self.config.get("max_messages_per_user", 1000)
        if len(user_data["messages"]) > max_messages:
            user_data["messages"] = user_data["messages"][-max_messages:]
        
# 更新活跃时间模式
        try:
            hour = int((timestamp % 86400) / 3600)  # 一天中的小时数
            hour_str = str(hour)
            if "activity_pattern" not in user_data:
                user_data["activity_pattern"] = {}
            user_data["activity_pattern"][hour_str] = user_data["activity_pattern"].get(hour_str, 0) + 1
        except:
            pass
        
        # 更新词频
        try:
            words = re.findall(r'[\w]+', content)
            for word in words:
                if len(word) > 1:  # 过滤单字
                    if "word_frequency" not in user_data:
                        user_data["word_frequency"] = {}
                    user_data["word_frequency"][word] = user_data["word_frequency"].get(word, 0) + 1
        except:
            pass
        
        # 情感分析
        try:
            emotion = self._analyze_emotion(content)
            if "emotion_scores" not in user_data:
                user_data["emotion_scores"] = []
            user_data["emotion_scores"].append(emotion)
            
            # 限制情感分数数量
            if len(user_data["emotion_scores"]) > 100:
                user_data["emotion_scores"] = user_data["emotion_scores"][-100:]
        except:
            pass
        
        # 保存用户数据
        self.user_data[user_name] = user_data
        
        # 更新全局统计
        self.global_stats["total_messages"] += 1
        if user_name not in self.global_stats["active_users"]:
            self.global_stats["active_users"].append(user_name)
        
        # 更新每日统计
        try:
            date_str = datetime.fromtimestamp(timestamp).date().isoformat()
            if date_str not in self.global_stats["daily_stats"]:
                self.global_stats["daily_stats"][date_str] = {"messages": 0, "users": []}
            
            self.global_stats["daily_stats"][date_str]["messages"] += 1
            if user_name not in self.global_stats["daily_stats"][date_str]["users"]:
                self.global_stats["daily_stats"][date_str]["users"].append(user_name)
        except:
            pass
        
        # 定期保存数据（每100条消息）
        if self.global_stats["total_messages"] % 100 == 0:
            self._save_data()    
    def _update_interaction(self, user_name: str, interaction_type: str):
        """更新用户互动记录"""
        try:
            if user_name not in self.user_data:
                self.user_data[user_name] = {
                    "first_seen": time.time(),
                    "last_seen": time.time(),
                    "message_count": 0,
                    "messages": [],
                    "interests": {},
                    "activity_pattern": {},
                    "word_frequency": {},
                    "emotion_scores": [],
                    "interaction_users": []
                }
            
            user_data = self.user_data[user_name]
            if "interaction_users" not in user_data:
                user_data["interaction_users"] = []
            
            # 记录互动类型（可选）
            if interaction_type not in user_data.get("interaction_types", {}):
                if "interaction_types" not in user_data:
                    user_data["interaction_types"] = {}
                user_data["interaction_types"][interaction_type] = 0
            user_data["interaction_types"][interaction_type] = user_data["interaction_types"].get(interaction_type, 0) + 1
        except Exception as e:
            print(f"更新用户互动记录失败: {e}")
    
    def _analyze_user_interest(self, user_name: str, content: str):
        """分析用户兴趣"""
        user_data = self.user_data.get(user_name, {})
        
        # 确保interests存在
        if "interests" not in user_data:
            user_data["interests"] = {}
        
        # 检查兴趣关键词
        for category, keywords in self.analysis_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    user_data["interests"][category] = user_data["interests"].get(category, 0) + 1
    
    def _analyze_emotion(self, content: str) -> float:
        """简单的情感分析"""
        # 正面情感词
        positive_words = ["哈哈", "嘻嘻", "开心", "快乐", "爱", "喜欢", "棒", "赞", "666", "👍", "😊", "😄", "🎉"]
        # 负面情感词
        negative_words = ["难过", "伤心", "讨厌", " hate", "糟糕", "垃圾", "😢", "😭", "😡", "👎"]
        
        content_lower = content.lower()
        positive_count = sum(1 for word in positive_words if word in content_lower)
        negative_count = sum(1 for word in negative_words if word in content_lower)
        
        # 计算情感分数 (-1 到 1)
        if positive_count + negative_count == 0:
            return 0.0
        
        return (positive_count - negative_count) / (positive_count + negative_count)
    
    def get_user_profile(self, user_name: str) -> Optional[Dict]:
        """获取用户画像"""
        user_data = self.user_data.get(user_name)
        if not user_data:
            return None
        
        # 计算用户等级
        message_count = user_data["message_count"]
        if message_count < 10:
            level = "新手"
        elif message_count < 50:
            level = "活跃"
        elif message_count < 200:
            level = "资深"
        else:
            level = "元老"
        
        # 获取主要兴趣
        interests = user_data["interests"]
        main_interests = sorted(interests.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # 获取活跃时段
        activity_pattern = user_data["activity_pattern"]
        most_active_hour = max(activity_pattern.items(), key=lambda x: x[1])[0] if activity_pattern else 0
        
        # 计算平均情感分数
        emotion_scores = user_data["emotion_scores"]
        avg_emotion = sum(emotion_scores) / len(emotion_scores) if emotion_scores else 0.0
        
        # 获取常用词汇
        common_words = sorted(user_data["word_frequency"].items(), key=lambda x: x[1], reverse=True)[:10]
        
        # 计算活跃度
        days_active = (datetime.now() - datetime.fromtimestamp(user_data["first_seen"])).days + 1
        activity_rate = message_count / days_active
        
        return {
            "user_name": user_name,
            "level": level,
            "message_count": message_count,
            "first_seen": datetime.fromtimestamp(user_data["first_seen"]).isoformat(),
            "last_seen": datetime.fromtimestamp(user_data["last_seen"]).isoformat(),
            "days_active": days_active,
            "activity_rate": round(activity_rate, 2),
            "main_interests": [{"category": cat, "count": count} for cat, count in main_interests],
            "most_active_hour": most_active_hour,
            "avg_emotion": round(avg_emotion, 2),
            "common_words": [{"word": word, "count": count} for word, count in common_words],
            "interaction_count": len(user_data["interaction_users"])
        }
    
    def get_global_analytics(self) -> Dict:
        """获取全局分析数据"""
        # 用户等级分布
        level_distribution = {}
        activity_threshold = self.config.get("user_activity_threshold", 10)
        
        active_users = 0
        for user_name, user_data in self.user_data.items():
            try:
                days_active = (datetime.now() - datetime.fromtimestamp(user_data["first_seen"])).days + 1
                activity_rate = user_data["message_count"] / days_active
                
                if activity_rate >= activity_threshold:
                    active_users += 1
                
                # 计算等级
                if user_data["message_count"] < 10:
                    level_distribution["新手"] = level_distribution.get("新手", 0) + 1
                elif user_data["message_count"] < 50:
                    level_distribution["活跃"] = level_distribution.get("活跃", 0) + 1
                elif user_data["message_count"] < 200:
                    level_distribution["资深"] = level_distribution.get("资深", 0) + 1
                else:
                    level_distribution["元老"] = level_distribution.get("元老", 0) + 1
            except:
                pass
        
        # 兴趣分布
        interest_distribution = {}
        for user_data in self.user_data.values():
            try:
                for category, count in user_data.get("interests", {}).items():
                    interest_distribution[category] = interest_distribution.get(category, 0) + count
            except:
                pass
        
        # 活跃时段分布
        hourly_activity = {}
        for user_data in self.user_data.values():
            try:
                for hour, count in user_data.get("activity_pattern", {}).items():
                    hourly_activity[hour] = hourly_activity.get(hour, 0) + count
            except:
                pass
        
        # 最近7天统计
        recent_stats = []
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).date().isoformat()
            day_stats = self.global_stats["daily_stats"].get(date, {"messages": 0, "users": set()})
            recent_stats.append({
                "date": date,
                "messages": day_stats["messages"],
                "users": len(day_stats["users"])
            })
        
        # 最活跃用户
        most_active_users = sorted(
            [(user, data["message_count"]) for user, data in self.user_data.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_messages": self.global_stats["total_messages"],
            "total_users": self.global_stats["total_users"],
            "active_users": active_users,
            "level_distribution": dict(level_distribution),
            "interest_distribution": dict(sorted(interest_distribution.items(), key=lambda x: x[1], reverse=True)),
            "hourly_activity": dict(hourly_activity),
            "recent_stats": recent_stats[::-1],  # 按时间正序
            "most_active_users": [{"user": user, "messages": count} for user, count in most_active_users]
        }
    
    def search_users_by_interest(self, interest: str) -> List[Dict]:
        """根据兴趣搜索用户"""
        matching_users = []
        
        for user_name, user_data in self.user_data.items():
            if interest in user_data["interests"]:
                profile = self.get_user_profile(user_name)
                if profile:
                    matching_users.append(profile)
        
        # 按兴趣强度排序
        matching_users.sort(key=lambda x: next((c["count"] for c in x["main_interests"] if c["category"] == interest), 0), reverse=True)
        
        return matching_users
    
    def get_user_memory(self, user_name: str) -> Dict:
        """获取用户记忆信息"""
        user_data = self.user_data.get(user_name, {})
        if not user_data:
            return {"messages": [], "interests": {}, "common_topics": []}
        
        # 获取最近的消息
        recent_messages = user_data["messages"][-10:] if user_data["messages"] else []
        
        # 获取主要兴趣
        interests = dict(sorted(user_data["interests"].items(), key=lambda x: x[1], reverse=True))
        
        # 提取常见话题
        common_topics = []
        for word, count in user_data["word_frequency"].most_common(20):
            if len(word) > 1 and count > 3:  # 过滤单字和低频词
                common_topics.append({"word": word, "count": count})
        
        return {
            "messages": recent_messages,
            "interests": interests,
            "common_topics": common_topics,
            "emotion_trend": user_data["emotion_scores"][-20:] if user_data["emotion_scores"] else []
        }
    
    def update_config(self, new_config: Dict):
        """更新配置时重新解析关键词"""
        super().update_config(new_config)
        self._parse_keywords()
    
    def clear_old_data(self, days: int = 30):
        """清理旧数据"""
        cutoff_time = time.time() - (days * 24 * 3600)
        
        # 清理不活跃用户
        inactive_users = []
        for user_name, user_data in self.user_data.items():
            if user_data["last_seen"] < cutoff_time:
                inactive_users.append(user_name)
        
        for user in inactive_users:
            del self.user_data[user]
        
        # 清理旧的日统计
        cutoff_date = (datetime.now() - timedelta(days=days)).date().isoformat()
        old_dates = [date for date in self.global_stats["daily_stats"].keys() if date < cutoff_date]
        for date in old_dates:
            del self.global_stats["daily_stats"][date]
        
        # 保存数据
        self._save_data()
        
        print(f"已清理 {len(inactive_users)} 个不活跃用户和 {len(old_dates)} 天的旧数据")