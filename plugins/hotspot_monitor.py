# -*- coding: utf-8 -*-
"""
直播爆点监测插件
监测弹幕速度、礼物数量等指标，发现爆点时发送通知
"""

import time
import asyncio
from collections import deque, defaultdict
from typing import Optional, Dict, List
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase
from core.danmaku_sender import get_danmaku_sender


class HotspotMonitorPlugin(PluginBase):
    """直播爆点监测插件"""
    
    name = "爆点监测"
    description = "监测弹幕速度、礼物数量等指标，发现爆点时发送通知"
    version = "1.0.0"
    author = "BililiveRobot"
    
    config_schema = [
        {
            "key": "danmaku_speed_threshold",
            "label": "弹幕速度阈值（条/分钟）",
            "type": "number",
            "default": 60,
            "min": 10,
            "max": 500
        },
        {
            "key": "gift_value_threshold",
            "label": "礼物价值阈值（金瓜子/分钟）",
            "type": "number",
            "default": 10000,
            "min": 1000,
            "max": 1000000
        },
        {
            "key": "sc_count_threshold",
            "label": "SC数量阈值（个/分钟）",
            "type": "number",
            "default": 3,
            "min": 1,
            "max": 20
        },
        {
            "key": "monitor_window",
            "label": "监测窗口时间（秒）",
            "type": "number",
            "default": 60,
            "min": 30,
            "max": 300
        },
        {
            "key": "alert_cooldown",
            "label": "告警冷却时间（秒）",
            "type": "number",
            "default": 300,
            "min": 60,
            "max": 1800
        },
        {
            "key": "enable_auto_alert",
            "label": "启用自动弹幕告警",
            "type": "boolean",
            "default": True
        },
        {
            "key": "alert_message",
            "label": "告警消息模板",
            "type": "string",
            "default": "【爆点提醒】当前{type}：{value}，超过阈值{threshold}！"
        }
    ]
    
    def __init__(self):
        super().__init__()
        
        # 时间窗口数据
        self.monitor_window = self.config.get("monitor_window", 60)
        self.danmaku_times = deque(maxlen=self.monitor_window)
        self.gift_data = deque(maxlen=self.monitor_window)
        self.sc_data = deque(maxlen=self.monitor_window)
        self.guard_data = deque(maxlen=self.monitor_window)
        
        # 统计数据
        self.current_stats = {
            "danmaku_speed": 0,
            "gift_value_per_minute": 0,
            "sc_count_per_minute": 0,
            "guard_count_per_minute": 0,
            "is_hotspot": False,
            "hotspot_type": None,
            "hotspot_value": None
        }
        
        # 告警冷却
        self.last_alert_time = 0
        self.alert_cooldown = self.config.get("alert_cooldown", 300)
        
        # 爆点历史
        self.hotspot_history = []
    
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """处理弹幕事件"""
        current_time = time.time()
        
        # 记录弹幕时间
        self.danmaku_times.append(current_time)
        
        # 更新统计
        self._update_stats()
        
        # 检查爆点
        await self._check_hotspot()
        
        # 添加爆点信息到数据中
        data["hotspot"] = {
            "is_hotspot": self.current_stats["is_hotspot"],
            "type": self.current_stats["hotspot_type"],
            "value": self.current_stats["hotspot_value"],
            "stats": self.current_stats.copy()
        }
        
        return data
    
    async def on_gift(self, data: dict) -> Optional[dict]:
        """处理礼物事件"""
        current_time = time.time()
        
        # 记录礼物数据
        self.gift_data.append({
            "time": current_time,
            "value": data.get("total_coin", 0),
            "name": data.get("gift_name", ""),
            "user": data.get("user", {}).get("uname", "")
        })
        
        # 更新统计
        self._update_stats()
        
        # 检查爆点
        await self._check_hotspot()
        
        # 添加爆点信息
        data["hotspot"] = {
            "is_hotspot": self.current_stats["is_hotspot"],
            "type": self.current_stats["hotspot_type"],
            "value": self.current_stats["hotspot_value"],
            "stats": self.current_stats.copy()
        }
        
        return data
    
    async def on_superchat(self, data: dict) -> Optional[dict]:
        """处理SC事件"""
        current_time = time.time()
        
        # 记录SC数据
        self.sc_data.append({
            "time": current_time,
            "price": data.get("price", 0),
            "user": data.get("user", {}).get("uname", ""),
            "content": data.get("content", "")
        })
        
        # 更新统计
        self._update_stats()
        
        # 检查爆点
        await self._check_hotspot()
        
        # 添加爆点信息
        data["hotspot"] = {
            "is_hotspot": self.current_stats["is_hotspot"],
            "type": self.current_stats["hotspot_type"],
            "value": self.current_stats["hotspot_value"],
            "stats": self.current_stats.copy()
        }
        
        return data
    
    async def on_guard(self, data: dict) -> Optional[dict]:
        """处理上舰事件"""
        current_time = time.time()
        
        # 记录上舰数据
        self.guard_data.append({
            "time": current_time,
            "level": data.get("guard_level", 3),
            "user": data.get("user", {}).get("uname", ""),
            "price": data.get("price", 0)
        })
        
        # 更新统计
        self._update_stats()
        
        # 检查爆点
        await self._check_hotspot()
        
        # 添加爆点信息
        data["hotspot"] = {
            "is_hotspot": self.current_stats["is_hotspot"],
            "type": self.current_stats["hotspot_type"],
            "value": self.current_stats["hotspot_value"],
            "stats": self.current_stats.copy()
        }
        
        return data
    
    def _update_stats(self):
        """更新统计数据"""
        current_time = time.time()
        window_start = current_time - self.monitor_window
        
        # 弹幕速度
        recent_danmaku = [t for t in self.danmaku_times if t >= window_start]
        self.current_stats["danmaku_speed"] = len(recent_danmaku) * (60 / self.monitor_window)
        
        # 礼物价值
        recent_gifts = [g for g in self.gift_data if g["time"] >= window_start]
        self.current_stats["gift_value_per_minute"] = sum(g["value"] for g in recent_gifts) * (60 / self.monitor_window)
        
        # SC数量
        recent_scs = [sc for sc in self.sc_data if sc["time"] >= window_start]
        self.current_stats["sc_count_per_minute"] = len(recent_scs) * (60 / self.monitor_window)
        
        # 上舰数量
        recent_guards = [g for g in self.guard_data if g["time"] >= window_start]
        self.current_stats["guard_count_per_minute"] = len(recent_guards) * (60 / self.monitor_window)
    
    async def _check_hotspot(self):
        """检查是否触发爆点"""
        thresholds = {
            "弹幕速度": (self.current_stats["danmaku_speed"], self.config.get("danmaku_speed_threshold", 60)),
            "礼物价值": (self.current_stats["gift_value_per_minute"], self.config.get("gift_value_threshold", 10000)),
            "SC数量": (self.current_stats["sc_count_per_minute"], self.config.get("sc_count_threshold", 3)),
            "上舰数量": (self.current_stats["guard_count_per_minute"], 1)  # 上舰超过1个就算爆点
        }
        
        # 检查各项指标
        for hotspot_type, (value, threshold) in thresholds.items():
            if value >= threshold:
                # 触发爆点
                self.current_stats["is_hotspot"] = True
                self.current_stats["hotspot_type"] = hotspot_type
                self.current_stats["hotspot_value"] = value
                
                # 发送告警
                await self._send_alert(hotspot_type, value, threshold)
                
                # 记录爆点历史
                self.hotspot_history.append({
                    "type": hotspot_type,
                    "value": value,
                    "threshold": threshold,
                    "time": time.time(),
                    "stats": self.current_stats.copy()
                })
                
                # 保留最近100条记录
                if len(self.hotspot_history) > 100:
                    self.hotspot_history = self.hotspot_history[-100:]
                
                return
        
        # 没有触发爆点
        self.current_stats["is_hotspot"] = False
        self.current_stats["hotspot_type"] = None
        self.current_stats["hotspot_value"] = None
    
    async def _send_alert(self, hotspot_type: str, value: float, threshold: float):
        """发送爆点告警"""
        current_time = time.time()
        
        # 检查冷却时间
        if current_time - self.last_alert_time < self.alert_cooldown:
            return
        
        # 更新最后告警时间
        self.last_alert_time = current_time
        
        # 是否启用自动告警
        if not self.config.get("enable_auto_alert", True):
            return
        
        # 构建告警消息
        alert_template = self.config.get("alert_message", "【爆点提醒】当前{type}：{value}，超过阈值{threshold}！")
        
        # 格式化数值
        if hotspot_type == "礼物价值":
            value_str = f"{value:.0f}金瓜子/分钟"
            threshold_str = f"{threshold:.0f}金瓜子/分钟"
        elif hotspot_type == "弹幕速度":
            value_str = f"{value:.0f}条/分钟"
            threshold_str = f"{threshold:.0f}条/分钟"
        elif hotspot_type == "SC数量":
            value_str = f"{value:.0f}个/分钟"
            threshold_str = f"{threshold:.0f}个/分钟"
        else:
            value_str = f"{value:.0f}个/分钟"
            threshold_str = f"{threshold:.0f}个/分钟"
        
        alert_message = alert_template.format(
            type=hotspot_type,
            value=value_str,
            threshold=threshold_str
        )
        
        # 发送弹幕
        sender = get_danmaku_sender()
        if sender:
            await sender.send(alert_message)
            print(f"爆点告警已发送: {alert_message}")
    
    def get_current_stats(self) -> Dict:
        """获取当前统计数据"""
        return {
            "danmaku_speed": round(self.current_stats["danmaku_speed"], 2),
            "gift_value_per_minute": round(self.current_stats["gift_value_per_minute"], 2),
            "sc_count_per_minute": round(self.current_stats["sc_count_per_minute"], 2),
            "guard_count_per_minute": round(self.current_stats["guard_count_per_minute"], 2),
            "is_hotspot": self.current_stats["is_hotspot"],
            "hotspot_type": self.current_stats["hotspot_type"],
            "hotspot_value": self.current_stats["hotspot_value"]
        }
    
    def get_hotspot_summary(self) -> Dict:
        """获取爆点统计摘要"""
        if not self.hotspot_history:
            return {
                "total_hotspots": 0,
                "hotspot_types": {},
                "recent_hotspots": []
            }
        
        # 统计各类型爆点次数
        hotspot_types = defaultdict(int)
        for hotspot in self.hotspot_history:
            hotspot_types[hotspot["type"]] += 1
        
        # 最近的爆点
        recent_hotspots = sorted(
            self.hotspot_history,
            key=lambda x: x["time"],
            reverse=True
        )[:10]
        
        return {
            "total_hotspots": len(self.hotspot_history),
            "hotspot_types": dict(hotspot_types),
            "recent_hotspots": recent_hotspots,
            "current_stats": self.current_stats
        }
    
    def reset_history(self):
        """重置历史数据"""
        self.hotspot_history.clear()
        self.danmaku_times.clear()
        self.gift_data.clear()
        self.sc_data.clear()
        self.guard_data.clear()
        self.current_stats = {
            "danmaku_speed": 0,
            "gift_value_per_minute": 0,
            "sc_count_per_minute": 0,
            "guard_count_per_minute": 0,
            "is_hotspot": False,
            "hotspot_type": None,
            "hotspot_value": None
        }
        print("爆点监测历史数据已重置")