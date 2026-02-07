# -*- coding: utf-8 -*-
"""
签到和抽签插件
提供用户签到、连续签到奖励、抽签等功能
"""

import time
import random
import json
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase
from core.plugin_base import PluginBaseEnhanced
from core.danmaku_sender import get_danmaku_sender


class CheckinLotteryPlugin(PluginBaseEnhanced):
    """签到和抽签插件"""
    
    name = "签到抽签"
    description = "提供用户签到、连续签到奖励、抽签等功能"
    version = "1.0.0"
    author = "BililiveRobot"
    
    config_schema = [
        {
            "key": "enable_checkin",
            "label": "启用签到功能",
            "type": "boolean",
            "default": True
        },
        {
            "key": "enable_lottery",
            "label": "启用抽签功能",
            "type": "boolean",
            "default": True
        },
        {
            "key": "checkin_command",
            "label": "签到命令",
            "type": "string",
            "default": "签到"
        },
        {
            "key": "lottery_command",
            "label": "抽签命令",
            "type": "string",
            "default": "抽签"
        },
        {
            "key": "continuous_checkin_rewards",
            "label": "连续签到奖励（JSON格式）",
            "type": "string",
            "default": '{"3": "小星星✨", "7": "月亮🌙", "15": "太阳☀️", "30": "皇冠👑"}'
        },
        {"key": "lottery_rewards", "label": "抽签奖励列表（JSON格式）", "type": "string", "default": '{"1": {"name": "谢谢参与", "weight": 40, "message": "谢谢参与"}, "2": {"name": "小幸运", "weight": 30, "message": "小幸运✨"}, "3": {"name": "中幸运", "weight": 20, "message": "中幸运🌟"}, "4": {"name": "大幸运", "weight": 8, "message": "大幸运⭐"}, "5": {"name": "超级幸运", "weight": 2, "message": "超级幸运🌠"}}'},
        {
            "key": "lottery_cooldown",
            "label": "抽签冷却时间（小时）",
            "type": "number",
            "default": 1,
            "min": 0,
            "max": 24
        },
        {"key": "checkin_messages", "label": "签到成功消息列表", "type": "array", "default": ["{user} 签到成功！", "签到成功！{user}", "签到完成！{user}", "{user} 已签到"]}
    ]
    
    def __init__(self):
        super().__init__()
        
        # 用户签到数据
        self.user_checkins = {}  # 用户名 -> 签到数据
        self.user_lotteries = {}  # 用户名 -> 抽签数据
        
        # 加载保存的数据
        self._load_data()
        
        # 解析奖励配置
        self.continuous_rewards = {}
        self.lottery_rewards = []
        self._parse_rewards()
    
    def _load_data(self):
        """加载保存的数据"""
        try:
            # 加载签到数据
            checkin_file = "./data/checkin_data.json"
            if os.path.exists(checkin_file):
                with open(checkin_file, "r", encoding="utf-8") as f:
                    self.user_checkins = json.load(f)
            
            # 加载抽签数据
            lottery_file = "./data/lottery_data.json"
            if os.path.exists(lottery_file):
                with open(lottery_file, "r", encoding="utf-8") as f:
                    self.user_lotteries = json.load(f)
        except Exception as e:
            print(f"加载签到抽签数据失败: {e}")
    
    def _save_data(self):
        """保存数据"""
        try:
            os.makedirs("./data", exist_ok=True)
            
            # 保存签到数据
            checkin_file = "./data/checkin_data.json"
            with open(checkin_file, "w", encoding="utf-8") as f:
                json.dump(self.user_checkins, f, ensure_ascii=False, indent=2)
            
            # 保存抽签数据
            lottery_file = "./data/lottery_data.json"
            with open(lottery_file, "w", encoding="utf-8") as f:
                json.dump(self.user_lotteries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存签到抽签数据失败: {e}")
    
    def _parse_rewards(self):
        """解析奖励配置"""
        try:
            # 解析连续签到奖励
            rewards_str = self.config.get("continuous_checkin_rewards", "{}")
            self.continuous_rewards = json.loads(rewards_str)
            
            # 解析抽签奖励
            lottery_str = self.config.get("lottery_rewards", "{}")
            lottery_data = json.loads(lottery_str)
            
            # 构建权重列表
            self.lottery_rewards = []
            for level, reward in lottery_data.items():
                self.lottery_rewards.append({
                    "level": int(level),
                    "name": reward["name"],
                    "weight": reward["weight"],
                    "message": reward["message"]
                })
            
            # 按权重排序
            self.lottery_rewards.sort(key=lambda x: x["weight"])
        except Exception as e:
            print(f"解析奖励配置失败: {e}")
    
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """处理弹幕事件"""
        # 检查是否为机器人自己的消息
        if self.is_bot_message(data):
            return data

        if not (self.config.get("enable_checkin", True) or self.config.get("enable_lottery", True)):
            return data

        content = data.get("content", "").strip()
        user_name = data.get("user", {}).get("uname", "")

        if not user_name or not content:
            return data

        current_time = time.time()

        # 处理签到
        if self.config.get("enable_checkin", True):
            checkin_command = self.config.get("checkin_command", "签到").strip()
            print(f"[签到插件] 检查弹幕内容: '{content}', 命令: '{checkin_command}', 匹配: {content == checkin_command}")
            if content == checkin_command:
                print(f"[签到插件] 触发签到，用户: {user_name}")
                await self._handle_checkin(user_name, current_time)

        # 处理抽签
        if self.config.get("enable_lottery", True):
            lottery_command = self.config.get("lottery_command", "抽签").strip()
            if content == lottery_command:
                await self._handle_lottery(user_name, current_time)

        return data
    
    async def _handle_checkin(self, user_name: str, current_time: float):
        """处理签到"""
        print(f"[签到插件] 开始处理签到，用户: {user_name}")
        # 获取用户签到数据
        user_data = self.user_checkins.get(user_name, {
            "last_checkin": 0,
            "continuous_days": 0,
            "total_days": 0,
            "checkin_dates": []
        })

        # 检查今天是否已签到
        today = datetime.fromtimestamp(current_time).date()
        last_checkin_date = datetime.fromtimestamp(user_data["last_checkin"]).date()

        if today == last_checkin_date:
            # 今天已签到，回复已签到消息
            print(f"[签到插件] 用户 {user_name} 今天已签到")
            message = f"{user_name}你今天已经签到了，请不要重复签到哦"
            print(f"[签到插件] 准备发送已签到消息: {message}")
            await self._send_message(message)
            return

        # 计算连续签到天数
        if (today - last_checkin_date).days == 1:
            # 连续签到
            user_data["continuous_days"] += 1
        else:
            # 中断了，重新开始
            user_data["continuous_days"] = 1

        # 更新签到数据
        user_data["last_checkin"] = current_time
        user_data["total_days"] += 1
        user_data["checkin_dates"].append(today.isoformat())

        # 保留最近30天的签到记录
        if len(user_data["checkin_dates"]) > 30:
            user_data["checkin_dates"] = user_data["checkin_dates"][-30:]

        # 保存数据
        self.user_checkins[user_name] = user_data
        self._save_data()

        # 发送签到成功消息 - 简洁版本
        message = "签到成功！"
        print(f"[签到插件] 准备发送签到消息: {message}")
        
        await self._send_message(message)

        # 检查连续签到奖励
        await self._check_continuous_reward(user_name, user_data["continuous_days"])
    
    async def _check_continuous_reward(self, user_name: str, days: int):
        """检查连续签到奖励"""
        for threshold, reward in self.continuous_rewards.items():
            if days == int(threshold):
                # 简化奖励消息 - 不包含用户名
                if "小星星" in reward:
                    message = "获得小星星✨"
                elif "月亮" in reward:
                    message = "获得月亮🌙"
                elif "太阳" in reward:
                    message = "获得太阳☀️"
                elif "皇冠" in reward:
                    message = "获得皇冠👑"
                else:
                    message = "签到奖励！"
                
                # 确保不超过20字符
                if len(message) > 20:
                    message = message[:20]
                
                await self._send_message(message)
                break
    
    async def _handle_lottery(self, user_name: str, current_time: float):
        """处理抽签"""
        # 获取用户抽签数据
        user_data = self.user_lotteries.get(user_name, {
            "last_lottery": 0,
            "total_lotteries": 0,
            "lottery_history": []
        })
        
        # 检查冷却时间
        cooldown_hours = self.config.get("lottery_cooldown", 1)
        cooldown_seconds = cooldown_hours * 3600
        
        if current_time - user_data["last_lottery"] < cooldown_seconds:
            # 还在冷却中
            remaining_time = cooldown_seconds - (current_time - user_data["last_lottery"])
            remaining_hours = int(remaining_time // 3600)
            remaining_minutes = int((remaining_time % 3600) // 60)
            
            if remaining_hours > 0:
                time_str = f"{remaining_hours}小时"
            else:
                time_str = f"{remaining_minutes}分钟"
            
            message = f"{user_name[:8]} 冷却{time_str}"
            # 确保不超过20字符
            if len(message) > 20:
                message = f"{user_name[:6]} 冷却中"
            
            await self._send_message(message)
            return
        
        # 执行抽签
        reward = self._draw_lottery()
        
        if reward:
            # 更新用户数据
            user_data["last_lottery"] = current_time
            user_data["total_lotteries"] += 1
            user_data["lottery_history"].append({
                "reward": reward["name"],
                "time": current_time
            })
            
            # 保留最近20次抽签记录
            if len(user_data["lottery_history"]) > 20:
                user_data["lottery_history"] = user_data["lottery_history"][-20:]
            
            # 保存数据
            self.user_lotteries[user_name] = user_data
            self._save_data()
            
            # 发送抽签结果 - 简化消息
            reward_msg = reward['message']
            # 提取关键奖励信息
            if "谢谢参与" in reward_msg:
                reward_text = "谢谢参与"
            elif "小幸运" in reward_msg:
                reward_text = "小幸运✨"
            elif "中幸运" in reward_msg:
                reward_text = "中幸运🌟"
            elif "大幸运" in reward_msg:
                reward_text = "大幸运⭐"
            elif "超级幸运" in reward_msg:
                reward_text = "超级幸运🌠"
            else:
                reward_text = "抽签成功"
            
            message = f"{user_name[:10]} {reward_text}"
            # 确保不超过20字符
            if len(message) > 20:
                message = f"{user_name[:8]} {reward_text[:8]}"
            
            await self._send_message(message)
    
    def _draw_lottery(self) -> Optional[Dict]:
        """执行抽签"""
        if not self.lottery_rewards:
            return None
        
        # 计算总权重
        total_weight = sum(reward["weight"] for reward in self.lottery_rewards)
        
        # 随机选择
        random_num = random.randint(1, total_weight)
        current_weight = 0
        
        for reward in self.lottery_rewards:
            current_weight += reward["weight"]
            if random_num <= current_weight:
                return reward
        
        return self.lottery_rewards[0]  # 默认返回第一个
    
    async def _send_message(self, message: str):
        """发送消息"""
        print(f"[签到插件] 发送消息: {message}")
        sender = get_danmaku_sender()
        if sender:
            result = await sender.send(message)
            print(f"[签到插件] 发送结果: {result}")
            if not result.get("success"):
                print(f"消息发送失败: {result.get('message')}")
        else:
            print(f"[签到插件] 警告: 弹幕发送器未初始化")
    
    def get_checkin_stats(self) -> Dict:
        """获取签到统计"""
        today = datetime.now().date()
        today_checkins = 0
        total_users = len(self.user_checkins)
        
        for user_data in self.user_checkins.values():
            last_checkin_date = datetime.fromtimestamp(user_data["last_checkin"]).date()
            if last_checkin_date == today:
                today_checkins += 1
        
        # 连续签到排行
        top_users = sorted(
            [(user, data["continuous_days"]) for user, data in self.user_checkins.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_users": total_users,
            "today_checkins": today_checkins,
            "top_users": [{"user": user, "days": days} for user, days in top_users]
        }
    
    def get_lottery_stats(self) -> Dict:
        """获取抽签统计"""
        total_lotteries = sum(data["total_lotteries"] for data in self.user_lotteries.values())
        
        # 统计各等级中奖次数
        reward_stats = {}
        for user_data in self.user_lotteries.values():
            for history in user_data["lottery_history"]:
                reward_name = history["reward"]
                reward_stats[reward_name] = reward_stats.get(reward_name, 0) + 1
        
        # 抽签次数排行
        top_users = sorted(
            [(user, data["total_lotteries"]) for user, data in self.user_lotteries.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_lotteries": total_lotteries,
            "reward_stats": reward_stats,
            "top_users": [{"user": user, "count": count} for user, count in top_users]
        }
    
    def update_config(self, new_config: Dict):
        """更新配置时重新解析奖励"""
        super().update_config(new_config)
        self._parse_rewards()
    
    def reset_user_data(self, user_name: str = None):
        """重置用户数据"""
        if user_name:
            # 重置单个用户
            self.user_checkins.pop(user_name, None)
            self.user_lotteries.pop(user_name, None)
            print(f"已重置用户 {user_name} 的数据")
        else:
            # 重置所有用户
            self.user_checkins.clear()
            self.user_lotteries.clear()
            print("已重置所有用户数据")
        
        self._save_data()