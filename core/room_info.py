# -*- coding: utf-8 -*-
"""
B站直播间信息获取模块
"""

import time
import httpx
from typing import Dict, Optional
from core.wbi_sign import sign_params


class RoomInfo:
    """直播间信息获取器"""
    
    # API端点
    ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
    ROOM_INIT_URL = "https://api.live.bilibili.com/room/v1/Room/room_init"
    ANCHOR_INFO_URL = "https://api.live.bilibili.com/live_user/v1/Master/get_anchor_info"
    
    def __init__(self, room_id: int):
        self.room_id = room_id
        self.cache = {}
        self.cache_time = 60  # 缓存60秒
        
    async def get_room_info(self, force_refresh: bool = False) -> Dict:
        """获取直播间信息"""
        cache_key = "room_info"
        current_time = time.time()
        
        # 检查缓存
        if not force_refresh and cache_key in self.cache:
            cache_data = self.cache[cache_key]
            if current_time - cache_data["time"] < self.cache_time:
                return cache_data["data"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 获取房间信息
                params = {"room_id": self.room_id}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": f"https://live.bilibili.com/{self.room_id}"
                }
                response = await client.get(self.ROOM_INFO_URL, params=params, headers=headers)
                
                print(f"[调试] 房间信息API响应: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"[调试] 房间信息数据: {data}")
                    if data.get("code") == 0:
                        room_data = data["data"]
                        
                        # 解析直播开始时间
                        live_start_time = room_data.get("live_start_time", 0)
                        live_time_str = room_data.get("live_time", "")
                        
                        # 尝试从live_time字符串解析时间
                        if live_time_str:
                            try:
                                import datetime
                                # live_time格式: "2026-02-04 21:47:50"
                                live_time_dt = datetime.datetime.strptime(live_time_str, "%Y-%m-%d %H:%M:%S")
                                live_start_time = int(live_time_dt.timestamp())
                            except:
                                pass
                        
                        live_duration = 0
                        if live_start_time > 0:
                            live_duration = int(time.time() - live_start_time)
                        
                        result = {
                            "room_id": room_data.get("room_id", self.room_id),
                            "title": room_data.get("title", ""),
                            "description": room_data.get("description", ""),
                            "live_status": room_data.get("live_status", 0),  # 0:未开播 1:直播中 2:轮播
                            "live_start_time": live_start_time,
                            "live_duration": live_duration,
                            "live_time": room_data.get("live_time", ""),  # 原始时间字符串
                            "keyframe": room_data.get("keyframe", ""),
                            "online": room_data.get("online", 0),
                            "uid": room_data.get("uid", 0),
                            "area_name": room_data.get("area_name", ""),
                            "parent_area_name": room_data.get("parent_area_name", ""),
                            "tags": room_data.get("tags", ""),
                            "attention": room_data.get("attention", 0),  # 关注数
                        }
                        
                        # 缓存结果
                        self.cache[cache_key] = {
                            "data": result,
                            "time": current_time
                        }
                        
                        return result
        except Exception as e:
            print(f"获取直播间信息失败: {e}")
            
        # 返回缓存数据或默认值
        if cache_key in self.cache:
            return self.cache[cache_key]["data"]
        
        return {
            "room_id": self.room_id,
            "title": "",
            "description": "",
            "live_status": 0,
            "live_start_time": 0,
            "live_duration": 0,
            "online": 0,
            "area_name": "",
            "parent_area_name": "",
            "tags": "",
        }
    
    async def get_anchor_info(self, force_refresh: bool = False) -> Dict:
        """获取主播信息"""
        cache_key = "anchor_info"
        current_time = time.time()
        
        # 检查缓存
        if not force_refresh and cache_key in self.cache:
            cache_data = self.cache[cache_key]
            if current_time - cache_data["time"] < self.cache_time:
                return cache_data["data"]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 获取主播信息
                params = {"roomid": self.room_id}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": f"https://live.bilibili.com/{self.room_id}"
                }
                response = await client.get(self.ANCHOR_INFO_URL, params=params, headers=headers)
                
                print(f"[调试] 主播信息API响应: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"[调试] 主播信息数据: {data}")
                    if data.get("code") == 0 and data.get("data"):
                        info = data["data"].get("info", {})
                        
                        result = {
                            "uid": info.get("uid", 0),
                            "uname": info.get("uname", ""),
                            "face": info.get("face", ""),
                            "gender": info.get("gender", "保密"),
                            "sign": info.get("sign", ""),
                            "level": info.get("platform_user_level", 0),  # 主播等级
                            "follower_num": 0,  # 这个API可能不返回粉丝数
                            "room_id": self.room_id,
                        }
                        
                        # 尝试从room_news获取粉丝数
                        room_news = data["data"].get("room_news", {})
                        if room_news:
                            result["follower_num"] = room_news.get("followers", 0)
                        
                        # 缓存结果
                        self.cache[cache_key] = {
                            "data": result,
                            "time": current_time
                        }
                        
                        return result
        except Exception as e:
            print(f"获取主播信息失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 如果主播信息API失败，尝试从房间信息中获取基本信息
        try:
            room_info = await self.get_room_info()
            if room_info and room_info.get("uid"):
                # 使用用户信息API获取主播名称
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        user_info_url = f"https://api.bilibili.com/x/space/acc/info?mid={room_info['uid']}"
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        }
                        response = await client.get(user_info_url, headers=headers)
                        if response.status_code == 200:
                            user_data = response.json()
                            if user_data.get("code") == 0 and user_data.get("data"):
                                user_info_data = user_data["data"]
                                result = {
                                    "uid": room_info["uid"],
                                    "uname": user_info_data.get("name", ""),
                                    "face": user_info_data.get("face", ""),
                                    "gender": user_info_data.get("sex", "保密"),
                                    "sign": user_info_data.get("sign", ""),
                                    "level": user_info_data.get("level", 0),
                                    "follower_num": room_info.get("attention", 0),
                                    "room_id": self.room_id,
                                }
                                
                                # 缓存结果
                                self.cache[cache_key] = {
                                    "data": result,
                                    "time": current_time
                                }
                                
                                print(f"[调试] 从用户信息API获取主播数据成功: {result}")
                                return result
                except Exception as e2:
                    print(f"从用户信息API获取主播数据失败: {e2}")
        except Exception as e3:
            print(f"备用方案失败: {e3}")
            
        # 返回缓存数据或默认值
        if cache_key in self.cache:
            return self.cache[cache_key]["data"]
        
        return {
            "uid": 0,
            "uname": "",
            "face": "",
            "gender": "保密",
            "sign": "",
            "level": 0,
            "follower_num": 0,
            "room_id": self.room_id,
        }
    
    def format_duration(self, seconds: int) -> str:
        """格式化时长"""
        if seconds <= 0:
            return "未开播"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        else:
            return f"{minutes}分钟"
    
    async def handle_room_query(self, question: str) -> Optional[str]:
        """处理直播间信息查询"""
        try:
            # 解析问题类型
            question_lower = question.lower()
            
            # 当前时间查询
            if any(keyword in question for keyword in ["现在几点", "当前时间", "现在是什么时间", "几点了"]):
                from datetime import datetime
                now = datetime.now()
                return f"现在是{now.hour}点{now.minute}分~"
            
            # 获取直播间信息
            room_info = await self.get_room_info()
            anchor_info = await self.get_anchor_info()
            
            # 直播时长查询
            if any(keyword in question for keyword in ["直播了多久", "直播时长", "开播多久", "直播时间", "开播时间"]):
                if room_info["live_status"] == 1:
                    duration = self.format_duration(room_info["live_duration"])
                    return f"已经直播{duration}啦~"
                else:
                    return "主播还没开播哦~"
            
            # 直播状态查询
            if any(keyword in question for keyword in ["在直播吗", "正在直播", "直播状态", "开播了吗"]):
                if room_info["live_status"] == 1:
                    return "正在直播中，欢迎来看~"
                elif room_info["live_status"] == 2:
                    return "正在轮播中哦~"
                else:
                    return "主播还没开播呢~"
            
            # 直播标题查询
            if any(keyword in question for keyword in ["直播标题", "直播内容", "在播什么"]):
                title = room_info.get("title", "")
                if title:
                    return f"正在直播：{title}"
                else:
                    return "暂时没有获取到直播标题~"
            
            # 在线人数查询
            if any(keyword in question for keyword in ["多少人", "在线人数", "人气", "人气值", "观众数"]):
                online = room_info.get("online", 0)
                if online > 10000:
                    return f"当前有{online//10000}万人在线~"
                else:
                    return f"当前有{online}人在线~"
            
            # 主播信息查询
            if any(keyword in question for keyword in ["主播是谁", "主播名字", "谁是主播"]):
                uname = anchor_info.get("uname", "")
                if uname:
                    return f"主播是{uname}~"
                else:
                    return "暂时无法获取主播信息~"
            
            # 粉丝数查询
            if any(keyword in question for keyword in ["多少粉丝", "粉丝数", "关注人数"]):
                follower_num = anchor_info.get("follower_num", 0)
                if follower_num > 0:
                    if follower_num > 10000:
                        return f"主播有{follower_num//10000}万粉丝~"
                    else:
                        return f"主播有{follower_num}个粉丝~"
                else:
                    return "暂时无法获取粉丝数~"
            
            # 直播分区查询
            if any(keyword in question for keyword in ["直播分区", "什么分区", "分区"]):
                area = room_info.get("area_name", "")
                parent_area = room_info.get("parent_area_name", "")
                if area and parent_area:
                    return f"直播间在{parent_area} > {area}分区~"
                elif area:
                    return f"直播间在{area}分区~"
                else:
                    return "暂时无法获取分区信息~"
            
            return None
            
        except Exception as e:
            print(f"处理直播间查询失败: {e}")
            return None


# 全局实例
_room_info_instance = None


async def get_real_time_popularity(room_id: int) -> int:
    """获取实时人气值"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 使用Web API获取实时人气
            url = f"https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom?room_id={room_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"https://live.bilibili.com/{room_id}"
            }
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    room_info = data.get("data", {}).get("room_info", {})
                    return room_info.get("online", 0)
    except Exception as e:
        print(f"获取实时人气值失败: {e}")
    return 0


def get_room_info(room_id: int) -> RoomInfo:
    """获取直播间信息实例"""
    global _room_info_instance
    if _room_info_instance is None or _room_info_instance.room_id != room_id:
        _room_info_instance = RoomInfo(room_id)
    return _room_info_instance