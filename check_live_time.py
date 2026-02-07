#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查直播时间的不同字段
"""

import asyncio
import httpx
import json
import time

async def check_live_time():
    """检查直播时间的不同字段"""
    print("检查直播时间字段")
    print("=" * 50)
    
    room_id = 1837226318
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 获取房间信息
        url = "https://api.live.bilibili.com/room/v1/Room/get_info"
        params = {"room_id": room_id}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://live.bilibili.com/{room_id}"
        }
        
        response = await client.get(url, params=params, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                room_data = data["data"]
                
                print("所有时间相关字段:")
                print("-" * 50)
                
                # 检查所有可能的时间字段
                time_fields = [
                    "live_start_time",
                    "live_time", 
                    "start_time",
                    "room_info",  # 可能包含时间信息
                    "keyframe",
                    "lock_time",
                    "hidden_time",
                    "broadcast_type"
                ]
                
                for field in time_fields:
                    if field in room_data:
                        value = room_data[field]
                        print(f"{field}: {value}")
                        
                        # 如果是时间戳，转换为可读时间
                        if isinstance(value, (int, float)) and value > 0:
                            if value > 10000000000:  # 可能是毫秒时间戳
                                readable = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(value/1000))
                                print(f"  -> 可读时间: {readable}")
                            else:  # 可能是秒时间戳
                                readable = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(value))
                                print(f"  -> 可读时间: {readable}")
                
                # 检查嵌套对象
                if "room_info" in room_data and isinstance(room_data["room_info"], dict):
                    print("\nroom_info 对象内容:")
                    print(json.dumps(room_data["room_info"], indent=2, ensure_ascii=False))
                
                # 尝试使用另一个API获取更详细的信息
                print("\n尝试获取直播详情...")
                detail_url = "https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom"
                detail_params = {"room_id": room_id}
                
                detail_response = await client.get(detail_url, params=detail_params, headers=headers)
                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    print(f"详情API响应: {json.dumps(detail_data, ensure_ascii=False)[:500]}...")

if __name__ == "__main__":
    asyncio.run(check_live_time())