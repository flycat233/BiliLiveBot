# -*- coding: utf-8 -*-
"""
FastAPI 主服务
提供 REST API 和 WebSocket 服务
"""

import asyncio
import json
import os
import re
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel
import uvicorn

from core.auth import BilibiliAuth
from core.danmaku import DanmakuClient
from core.plugin_system import PluginManager
from core.wbi_sign import set_wbi_cookies
from core.danmaku_sender import init_danmaku_sender
from core.logger import get_logger

# 创建全局日志记录器
logger = get_logger("server")


# 创建 FastAPI 应用
app = FastAPI(
    title="B站直播弹幕获取工具",
    description="实时获取B站直播弹幕、礼物、SC等信息",
    version="1.0.0"
)

# 模板引擎
templates = Jinja2Templates(directory="templates")

# 全局实例
auth_manager = BilibiliAuth(data_dir="./data")
plugin_manager = PluginManager(plugin_dir="./plugins")
danmaku_client: Optional[DanmakuClient] = None

# 定时任务
hotspot_broadcast_task = None

# WebSocket 连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()


# ==================== 数据模型 ====================

class QRCodePollRequest(BaseModel):
    qrcode_key: str

class PluginToggleRequest(BaseModel):
    plugin_name: str
    enabled: bool

class PluginConfigRequest(BaseModel):
    plugin_name: str
    config: Dict

class RoomConnectRequest(BaseModel):
    room_id: int

class DanmakuSendRequest(BaseModel):
    message: str
    color: Optional[int] = 16777215  # 白色


# ==================== 前端页面 ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页"""
    return templates.TemplateResponse("index.html", {"request": request})


# ==================== 认证相关 API ====================

@app.get("/api/auth/status")
async def get_auth_status():
    """获取登录状态"""
    status = auth_manager.get_status()
    return JSONResponse(content=status)

@app.post("/api/auth/qrcode")
async def generate_qrcode():
    """生成登录二维码"""
    result = await auth_manager.generate_qrcode()
    return JSONResponse(content=result)

@app.post("/api/auth/qrcode/poll")
async def poll_qrcode(request: QRCodePollRequest):
    """轮询二维码状态"""
    result = await auth_manager.poll_qrcode_status(request.qrcode_key)

    # 如果登录成功，更新 WBI 签名器的 Cookie
    if result.get("success") and result.get("status") == "confirmed":
        cookies = auth_manager.get_cookies_dict()
        if cookies:
            set_wbi_cookies(cookies)

    return JSONResponse(content=result)

@app.post("/api/auth/anonymous")
async def set_anonymous():
    """切换到匿名模式"""
    auth_manager.set_anonymous()
    return JSONResponse(content={"success": True, "message": "已切换到匿名模式"})

@app.post("/api/auth/logout")
async def logout():
    """退出登录"""
    auth_manager.logout()
    # 清除 WBI 签名器的 Cookie
    set_wbi_cookies({})
    return JSONResponse(content={"success": True, "message": "已退出登录"})


# ==================== 直播间信息 API ====================

@app.get("/api/room/info/{room_id}")
async def get_room_info_api(room_id: int):
    """获取直播间详细信息"""
    try:
        from core.room_info import get_room_info
        
        room_info_instance = get_room_info(room_id)
        
        # 获取房间信息和主播信息
        room_data = await room_info_instance.get_room_info(force_refresh=True)
        anchor_data = await room_info_instance.get_anchor_info(force_refresh=True)
        
        # 如果主播名为空，尝试额外获取
        if not anchor_data.get("uname") and room_data.get("uid"):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    user_url = f"https://api.bilibili.com/x/space/acc/info?mid={room_data['uid']}"
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": f"https://live.bilibili.com/{room_id}"
                    }
                    resp = await client.get(user_url, headers=headers)
                    if resp.status_code == 200:
                        user_data = resp.json()
                        if user_data.get("code") == 0 and user_data.get("data"):
                            anchor_data["uname"] = user_data["data"].get("name", "")
                            anchor_data["uid"] = room_data["uid"]
                            print(f"[API] 通过用户API获取主播名: {anchor_data['uname']}")
            except Exception as e:
                print(f"[API] 额外获取主播名失败: {e}")
        
        # 合并数据
        result = {
            **room_data,
            "anchor": anchor_data,
            "live_duration_formatted": room_info_instance.format_duration(room_data.get("live_duration", 0))
        }
        
        print(f"[API] 返回数据 - 主播名: {anchor_data.get('uname', '无')}, UID: {room_data.get('uid', '无')}")
        
        return JSONResponse(content={"success": True, "data": result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"success": False, "message": f"获取直播间信息失败: {str(e)}"})


# ==================== 插件相关 API ====================

@app.get("/api/plugins/list")
async def get_plugin_list():
    """获取插件列表"""
    plugins = plugin_manager.get_plugin_list()
    return JSONResponse(content={"success": True, "plugins": plugins})

@app.post("/api/plugins/toggle")
async def toggle_plugin(request: PluginToggleRequest):
    """启用/禁用插件"""
    success = plugin_manager.toggle_plugin(request.plugin_name, request.enabled)
    if success:
        return JSONResponse(content={"success": True, "message": "操作成功"})
    else:
        return JSONResponse(content={"success": False, "message": "插件不存在"})

@app.post("/api/plugins/config")
async def update_plugin_config(request: PluginConfigRequest):
    """更新插件配置"""
    success = plugin_manager.update_plugin_config(request.plugin_name, request.config)
    if success:
        return JSONResponse(content={"success": True, "message": "配置已更新"})
    else:
        return JSONResponse(content={"success": False, "message": "插件不存在"})


# ==================== 直播间相关 API ====================

@app.get("/api/room/parse")
async def parse_room_url(url: str):
    """解析直播间 URL"""
    # 支持多种格式
    # https://live.bilibili.com/123456
    # live.bilibili.com/123456
    # 123456
    
    patterns = [
        r'live\.bilibili\.com/(\d+)',
        r'^(\d+)$'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            room_id = int(match.group(1))
            return JSONResponse(content={"success": True, "room_id": room_id})
    
    return JSONResponse(content={"success": False, "message": "无法解析直播间 URL"})


@app.post("/api/danmaku/send")
async def send_danmaku(request: DanmakuSendRequest):
    """发送弹幕"""
    from core.danmaku_sender import get_danmaku_sender
    
    sender = get_danmaku_sender()
    if sender is None:
        return JSONResponse(content={"success": False, "message": "未连接到直播间"})
    
    result = await sender.send(request.message, color=request.color)
    return JSONResponse(content=result)


# ==================== 用户分析相关 API ====================

@app.get("/api/analytics/global")
async def get_global_analytics():
    """获取全局分析数据"""
    user_analytics_plugin = plugin_manager.get_plugin("用户分析")
    
    if user_analytics_plugin and user_analytics_plugin.enabled:
        analytics = user_analytics_plugin.get_global_analytics()
        return JSONResponse(content={"success": True, "data": analytics})
    else:
        return JSONResponse(content={"success": False, "message": "用户分析插件未启用"})

@app.get("/api/analytics/user/{user_name}")
async def get_user_profile(user_name: str):
    """获取用户画像"""
    user_analytics_plugin = plugin_manager.get_plugin("用户分析")
    
    if user_analytics_plugin and user_analytics_plugin.enabled:
        profile = user_analytics_plugin.get_user_profile(user_name)
        if profile:
            return JSONResponse(content={"success": True, "data": profile})
        else:
            return JSONResponse(content={"success": False, "message": "用户不存在或数据不足"})
    else:
        return JSONResponse(content={"success": False, "message": "用户分析插件未启用"})

@app.get("/api/analytics/memory/{user_name}")
async def get_user_memory(user_name: str):
    """获取用户记忆"""
    user_analytics_plugin = plugin_manager.get_plugin("用户分析")
    
    if user_analytics_plugin and user_analytics_plugin.enabled:
        memory = user_analytics_plugin.get_user_memory(user_name)
        return JSONResponse(content={"success": True, "data": memory})
    else:
        return JSONResponse(content={"success": False, "message": "用户分析插件未启用"})

@app.get("/api/analytics/search")
async def search_users_by_interest(interest: str):
    """根据兴趣搜索用户"""
    user_analytics_plugin = plugin_manager.get_plugin("用户分析")
    
    if user_analytics_plugin and user_analytics_plugin.enabled:
        users = user_analytics_plugin.search_users_by_interest(interest)
        return JSONResponse(content={"success": True, "data": users})
    else:
        return JSONResponse(content={"success": False, "message": "用户分析插件未启用"})

@app.post("/api/analytics/clear-old-data")
async def clear_old_data(days: int = 30):
    """清理旧数据"""
    user_analytics_plugin = plugin_manager.get_plugin("用户分析")
    
    if user_analytics_plugin and user_analytics_plugin.enabled:
        user_analytics_plugin.clear_old_data(days)
        return JSONResponse(content={"success": True, "message": f"已清理{days}天前的旧数据"})
    else:
        return JSONResponse(content={"success": False, "message": "用户分析插件未启用"})

# ==================== 签到抽签相关 API ====================

@app.get("/api/checkin/stats")
async def get_checkin_stats():
    """获取签到统计"""
    checkin_plugin = plugin_manager.get_plugin("签到抽签")
    
    if checkin_plugin and checkin_plugin.enabled:
        stats = checkin_plugin.get_checkin_stats()
        return JSONResponse(content={"success": True, "data": stats})
    else:
        return JSONResponse(content={"success": False, "message": "签到抽签插件未启用"})

@app.get("/api/lottery/stats")
async def get_lottery_stats():
    """获取抽签统计"""
    checkin_plugin = plugin_manager.get_plugin("签到抽签")
    
    if checkin_plugin and checkin_plugin.enabled:
        stats = checkin_plugin.get_lottery_stats()
        return JSONResponse(content={"success": True, "data": stats})
    else:
        return JSONResponse(content={"success": False, "message": "签到抽签插件未启用"})


# ==================== WebSocket ====================

@app.websocket("/ws/danmaku")
async def websocket_danmaku(websocket: WebSocket):
    """弹幕推送 WebSocket"""
    # 获取查询参数中的token（如果有）
    token = websocket.query_params.get("token")

    # 添加身份验证
    if token:
        try:
            from core.auth_api import api_auth
            payload = api_auth.verify_token(token)
            if not payload:
                await websocket.close(code=1008, reason="无效的访问令牌")
                return
        except Exception as e:
            await websocket.close(code=1008, reason="身份验证失败")
            return

    await manager.connect(websocket)

    try:
        while True:
            # 接收客户端消息
            try:
                data = await websocket.receive_json()
            except Exception as e:
                # 如果接收消息失败，可能是连接已断开
                logger.warning(f"接收WebSocket消息失败: {e}")
                break

            action = data.get("action")

            if action == "connect":
                # 连接直播间
                room_id = data.get("room_id")
                await connect_room(room_id, websocket)

            elif action == "disconnect":
                # 断开连接
                await disconnect_room(websocket)
                break

            elif action == "ping":
                # 心跳
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception as e:
                    logger.warning(f"发送pong消息失败: {e}")
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket客户端断开连接")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
    finally:
        manager.disconnect(websocket)
        await disconnect_room(websocket)


async def connect_room(room_id: int, websocket: WebSocket):
    """连接到直播间"""
    global danmaku_client

    try:
        # 断开之前的连接
        if danmaku_client:
            await danmaku_client.disconnect()
            danmaku_client = None

        # 创建新客户端
        cookies = auth_manager.get_cookies_dict()
        danmaku_client = DanmakuClient(room_id, cookies)

        # 设置回调函数
        danmaku_client.on_danmaku = lambda data: handle_danmaku("danmaku", data)
        danmaku_client.on_gift = lambda data: handle_danmaku("gift", data)
        danmaku_client.on_superchat = lambda data: handle_danmaku("superchat", data)
        danmaku_client.on_guard = lambda data: handle_danmaku("guard", data)
        danmaku_client.on_interact = lambda data: handle_danmaku("interact", data)
        danmaku_client.on_online = lambda data: handle_danmaku("online", data)

        # 传递插件管理器引用
        danmaku_client.plugin_manager = plugin_manager

        # 初始化弹幕发送器
        init_danmaku_sender(cookies, room_id)
        logger.info(f"弹幕发送器已初始化，房间号: {room_id}")

        # 连接
        success = await danmaku_client.connect()

        # 检查WebSocket是否仍然连接
        if websocket.client_state.name != "CONNECTED":
            logger.warning("WebSocket已断开，取消连接")
            if danmaku_client:
                await danmaku_client.disconnect()
                danmaku_client = None
            return

        if success:
            try:
                await websocket.send_json({
                    "type": "connected",
                    "room_id": room_id,
                    "message": "连接成功"
                })
                logger.info(f"已向客户端发送连接成功消息，房间号: {room_id}")
            except Exception as send_error:
                logger.error(f"发送连接成功消息失败: {send_error}")
                # 发送失败，可能WebSocket已断开，清理客户端
                if danmaku_client:
                    await danmaku_client.disconnect()
                    danmaku_client = None
        else:
            # 连接失败，清理客户端
            await danmaku_client.disconnect()
            danmaku_client = None
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": "连接失败"
                })
                logger.warning("已向客户端发送连接失败消息")
            except Exception as send_error:
                logger.error(f"发送连接失败消息失败: {send_error}")

    except Exception as e:
        # 异常时清理客户端
        if danmaku_client:
            try:
                await danmaku_client.disconnect()
            except:
                pass
            danmaku_client = None

        # 尝试发送错误消息，但不让发送失败导致更多错误
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"连接失败: {str(e)}"
            })
        except Exception as send_error:
            logger.error(f"发送错误消息失败: {send_error}")


async def disconnect_room(websocket: WebSocket):
    """断开直播间连接"""
    global danmaku_client

    if danmaku_client:
        await danmaku_client.disconnect()
        danmaku_client = None

    # 只有在WebSocket仍然连接时才发送消息
    if websocket.client_state.name == "CONNECTED":
        try:
            await websocket.send_json({
                "type": "disconnected",
                "message": "已断开连接"
            })
        except Exception as e:
            logger.error(f"发送断开连接消息失败: {e}")


async def handle_danmaku(event_type: str, data: dict):
    """处理弹幕数据（通过插件系统）"""
    try:
        # 对于online事件，直接广播，不通过插件系统
        if event_type == "online":
            await manager.broadcast({
                "type": event_type,
                "data": data  # data已经是 {"online": xxx} 格式
            })
            return

        # 通过插件系统处理其他事件
        processed_data = await plugin_manager.process_event(event_type, data)

        # 如果插件返回 None，表示过滤掉该消息
        if processed_data is None:
            return

        # 广播到所有客户端
        await manager.broadcast({
            "type": event_type,
            "data": processed_data
        })

    except Exception as e:
        logger.error(f"处理弹幕错误: {e}")

async def auto_connect_room(room_id: int):
    """自动连接到直播间"""
    global danmaku_client
    
    try:
        # 等待一段时间确保服务器完全启动
        await asyncio.sleep(2)
        
        # 断开之前的连接
        if danmaku_client:
            await danmaku_client.disconnect()
            danmaku_client = None

        # 创建新客户端
        cookies = auth_manager.get_cookies_dict()
        danmaku_client = DanmakuClient(room_id, cookies)

        # 设置回调函数
        danmaku_client.on_danmaku = lambda data: handle_danmaku("danmaku", data)
        danmaku_client.on_gift = lambda data: handle_danmaku("gift", data)
        danmaku_client.on_superchat = lambda data: handle_danmaku("superchat", data)
        danmaku_client.on_guard = lambda data: handle_danmaku("guard", data)
        danmaku_client.on_interact = lambda data: handle_danmaku("interact", data)
        danmaku_client.on_online = lambda data: handle_danmaku("online", data)

        # 传递插件管理器引用
        danmaku_client.plugin_manager = plugin_manager

        # 初始化弹幕发送器
        init_danmaku_sender(cookies, room_id)
        logger.info(f"弹幕发送器已初始化，房间号: {room_id}")

        # 连接
        success = await danmaku_client.connect()
        
        if success:
            logger.info(f"自动连接到直播间 {room_id} 成功")
        else:
            logger.warning(f"自动连接到直播间 {room_id} 失败")
            
    except Exception as e:
        logger.error(f"自动连接直播间失败: {e}")


async def broadcast_hotspot_stats():
    """广播爆点统计数据"""
    try:
        hotspot_plugin = plugin_manager.get_plugin("爆点监测")
        if hotspot_plugin and hasattr(hotspot_plugin, 'get_current_stats'):
            stats = hotspot_plugin.get_current_stats()
            await manager.broadcast({
                "type": "hotspot_stats",
                "data": stats
            })
    except Exception as e:
        logger.error(f"广播爆点统计错误: {e}")


# ==================== 启动时加载插件 ====================


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info("正在加载插件...")
    plugin_manager.load_all_plugins()

    # 设置房间号到相关插件
    room_id = int(os.getenv("ROOM_ID", "1837226318"))  # 默认房间号修改为1837226318
    ai_plugin = plugin_manager.get_plugin("AI智能回复")
    if ai_plugin:
        ai_plugin.set_room_id(room_id)

    # 设置WebSocket管理器到插件系统
    plugin_manager.set_websocket_manager(manager)

    logger.info("插件加载完成")





    # 启动爆点统计广播任务


    global hotspot_broadcast_task


    async def hotspot_broadcast_loop():


        while True:


            await asyncio.sleep(10)  # 每10秒广播一次


            if manager.active_connections:  # 只有在有连接时才广播


                await broadcast_hotspot_stats()


    


    hotspot_broadcast_task = asyncio.create_task(hotspot_broadcast_loop())


    logger.info("爆点统计广播任务已启动")





    # 检查登录状态





        status = auth_manager.get_status()





        if status.get("logged_in"):





            logger.info(f"自动登录成功: {status.get('user_info', {}).get('uname', '未知用户')}")





            logger.info(f"用户等级: Lv{status.get('user_info', {}).get('level', 0)}")





    





            # 设置 WBI 签名器的 Cookie





            cookies = auth_manager.get_cookies_dict()





            if cookies:





                set_wbi_cookies(cookies)





                logger.info("已设置 WBI 签名器的 Cookie")





            





            # 自动连接到直播间





            logger.info(f"正在自动连接到直播间 {room_id}...")





            asyncio.create_task(auto_connect_room(room_id))





        else:





            logger.info("未检测到保存的登录凭证，请手动登录")


# ==================== 关闭时清理 ====================

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    logger.info("正在清理资源...")

    # 取消爆点统计广播任务
    global hotspot_broadcast_task
    if hotspot_broadcast_task:
        logger.info("正在停止爆点统计广播任务...")
        hotspot_broadcast_task.cancel()
        try:
            await asyncio.wait_for(hotspot_broadcast_task, timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("停止爆点统计广播任务超时")
        except:
            pass
        hotspot_broadcast_task = None

    # 断开直播间连接
    global danmaku_client
    if danmaku_client:
        logger.info("正在断开直播间连接...")
        try:
            await asyncio.wait_for(danmaku_client.disconnect(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("断开直播间连接超时")
        except Exception as e:
            logger.error(f"断开直播间连接时出错: {e}")
        danmaku_client = None

    # 关闭所有 WebSocket 连接
    logger.info("正在关闭 WebSocket 连接...")
    for connection in manager.active_connections[:]:
        try:
            await asyncio.wait_for(connection.close(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        except:
            pass
    manager.active_connections.clear()

    logger.info("资源清理完成")


# ==================== 主函数 ====================

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
