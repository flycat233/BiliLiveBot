# -*- coding: utf-8 -*-
"""
API扩展模块
添加新的API端点
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
from pydantic import BaseModel

from core.logger import get_logger
from core.database import db
from core.performance import performance_monitor
from core.cache import cache
from core.exporter import exporter
from core.auth_api import get_current_user
from core.config import get_config

logger = get_logger("api_extended")

# 创建路由
router = APIRouter(prefix="/api/v2", tags=["v2"])


# ==================== 数据模型 ====================

class ExportRequest(BaseModel):
    data_type: str  # user_analytics, danmaku_records, performance_metrics, error_logs
    format: str = "json"  # json, csv
    room_id: Optional[int] = None
    metric_name: Optional[str] = None
    hours: Optional[int] = 24
    limit: Optional[int] = 10000


# ==================== 性能监控API ====================

@router.get("/performance/metrics")
async def get_performance_metrics():
    """获取当前性能指标"""
    try:
        metrics = performance_monitor.get_current_metrics()
        return JSONResponse(content={"success": True, "data": metrics})
    except Exception as e:
        logger.error(f"获取性能指标失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/health")
async def get_health_status():
    """获取系统健康状态"""
    try:
        health = performance_monitor.get_health_status()
        return JSONResponse(content={"success": True, "data": health})
    except Exception as e:
        logger.error(f"获取健康状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 缓存管理API ====================

@router.get("/cache/stats")
async def get_cache_stats():
    """获取缓存统计信息"""
    try:
        stats = cache.get_stats()
        return JSONResponse(content={"success": True, "data": stats})
    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache():
    """清空缓存"""
    try:
        cache.clear()
        return JSONResponse(content={"success": True, "message": "缓存已清空"})
    except Exception as e:
        logger.error(f"清空缓存失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/cleanup")
async def cleanup_cache():
    """清理过期缓存"""
    try:
        cache.cleanup_expired()
        return JSONResponse(content={"success": True, "message": "过期缓存已清理"})
    except Exception as e:
        logger.error(f"清理缓存失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 数据库管理API ====================

@router.post("/database/backup")
async def backup_database():
    """备份数据库"""
    try:
        success = db.backup()
        if success:
            return JSONResponse(content={"success": True, "message": "数据库备份成功"})
        else:
            raise HTTPException(status_code=500, detail="数据库备份失败")
    except Exception as e:
        logger.error(f"数据库备份失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/database/cleanup")
async def cleanup_database(days: int = Query(30, ge=1, le=365)):
    """清理旧数据"""
    try:
        db.clean_old_data(days)
        return JSONResponse(content={
            "success": True,
            "message": f"已清理{days}天前的旧数据"
        })
    except Exception as e:
        logger.error(f"清理数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 数据导出API ====================

@router.post("/export")
async def export_data(request: ExportRequest):
    """导出数据"""
    try:
        if request.data_type == "user_analytics":
            filepath = exporter.export_user_analytics(request.format)
        
        elif request.data_type == "danmaku_records":
            filepath = exporter.export_danmaku_records(
                request.room_id,
                request.limit,
                request.format
            )
        
        elif request.data_type == "performance_metrics":
            if not request.metric_name:
                raise HTTPException(status_code=400, detail="需要指定metric_name")
            
            filepath = exporter.export_performance_metrics(
                request.metric_name,
                request.hours,
                request.format
            )
        
        elif request.data_type == "error_logs":
            filepath = exporter.export_error_logs(request.limit, request.format)
        
        else:
            raise HTTPException(status_code=400, detail=f"不支持的数据类型: {request.data_type}")
        
        return JSONResponse(content={
            "success": True,
            "filepath": filepath,
            "message": "数据导出成功"
        })
    
    except Exception as e:
        logger.error(f"数据导出失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/list")
async def list_exports():
    """获取导出文件列表"""
    try:
        files = exporter.get_export_list()
        return JSONResponse(content={"success": True, "data": files})
    except Exception as e:
        logger.error(f"获取导出列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/download/{filename}")
async def download_export(filename: str):
    """下载导出文件"""
    try:
        filepath = exporter.export_dir / filename
        
        if not filepath.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type='application/octet-stream'
        )
    except Exception as e:
        logger.error(f"下载文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/export/{filename}")
async def delete_export(filename: str):
    """删除导出文件"""
    try:
        success = exporter.delete_export(filename)
        
        if success:
            return JSONResponse(content={"success": True, "message": "文件已删除"})
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
    
    except Exception as e:
        logger.error(f"删除文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 用户分析API ====================

@router.get("/analytics/users")
async def get_all_users(limit: int = Query(100, ge=1, le=1000)):
    """获取所有用户分析数据"""
    try:
        users = db.get_all_users_analytics(limit)
        return JSONResponse(content={"success": True, "data": users})
    except Exception as e:
        logger.error(f"获取用户数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/user/{user_name}")
async def get_user_detail(user_name: str):
    """获取用户详细信息"""
    try:
        user = db.get_user_analytics(user_name)
        
        if user:
            return JSONResponse(content={"success": True, "data": user})
        else:
            raise HTTPException(status_code=404, detail="用户不存在")
    
    except Exception as e:
        logger.error(f"获取用户详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 配置管理API ====================

@router.get("/config")
async def get_config_api():
    """获取配置"""
    try:
        # 只返回非敏感配置
        safe_config = {
            "server": get_config("server"),
            "reconnect": get_config("reconnect"),
            "performance": get_config("performance"),
            "monitoring": get_config("monitoring"),
            "database": {
                "type": get_config("database.type"),
                "backup_enabled": get_config("database.backup_enabled"),
                "backup_interval_hours": get_config("database.backup_interval_hours")
            }
        }
        
        return JSONResponse(content={"success": True, "data": safe_config})
    except Exception as e:
        logger.error(f"获取配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 系统信息API ====================

@router.get("/system/info")
async def get_system_info():
    """获取系统信息"""
    try:
        import platform
        import sys
        
        info = {
            "platform": platform.platform(),
            "python_version": sys.version,
            "architecture": platform.machine(),
            "processor": platform.processor()
        }
        
        return JSONResponse(content={"success": True, "data": info})
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
