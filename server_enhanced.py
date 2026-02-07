# -*- coding: utf-8 -*-
"""
改进的服务器启动脚本
集成所有优化功能
"""

import asyncio
from pathlib import Path

from core.logger import get_logger
from core.config import config_manager, get_config
from core.database import db
from core.performance import performance_monitor
from core.cache import cache

logger = get_logger("server_enhanced")


async def startup_tasks():
    """启动任务"""
    logger.info("=" * 60)
    logger.info("BililiveRobot 增强版启动")
    logger.info("=" * 60)
    
    # 1. 加载配置
    logger.info("加载配置...")
    logger.info(f"服务器地址: {get_config('server.host')}:{get_config('server.port')}")
    logger.info(f"认证启用: {get_config('security.enable_auth')}")
    logger.info(f"自动重连: {get_config('reconnect.enable_auto_reconnect')}")
    logger.info(f"性能监控: {get_config('monitoring.enable_performance_monitor')}")
    
    # 2. 初始化数据库
    logger.info("初始化数据库...")
    # 数据库已在导入时初始化
    
    # 3. 启动性能监控
    if get_config('monitoring.enable_performance_monitor'):
        logger.info("启动性能监控...")
        interval = get_config('monitoring.metrics_interval_seconds', 60)
        await performance_monitor.start_monitoring(interval)
    
    # 4. 启动数据备份任务
    if get_config('database.backup_enabled'):
        logger.info("启动数据备份任务...")
        asyncio.create_task(backup_task())
    
    # 5. 启动缓存清理任务
    logger.info("启动缓存清理任务...")
    asyncio.create_task(cache_cleanup_task())
    
    logger.info("=" * 60)
    logger.info("所有启动任务完成")
    logger.info("=" * 60)


async def shutdown_tasks():
    """关闭任务"""
    logger.info("=" * 60)
    logger.info("BililiveRobot 正在关闭")
    logger.info("=" * 60)
    
    # 1. 停止性能监控
    logger.info("停止性能监控...")
    await performance_monitor.stop_monitoring()
    
    # 2. 备份数据库
    logger.info("备份数据库...")
    db.backup()
    
    # 3. 清理缓存
    logger.info("清理缓存...")
    cache.clear()
    
    # 4. 清理旧数据
    logger.info("清理旧数据...")
    days = get_config('database.cleanup_days', 30)
    db.clean_old_data(days)
    
    logger.info("=" * 60)
    logger.info("所有关闭任务完成")
    logger.info("=" * 60)


async def backup_task():
    """定期备份任务"""
    interval_hours = get_config('database.backup_interval_hours', 24)
    interval_seconds = interval_hours * 3600
    
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            logger.info("执行定期备份...")
            db.backup()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"备份任务错误: {e}", exc_info=True)


async def cache_cleanup_task():
    """定期清理缓存任务"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟清理一次
            cache.cleanup_expired()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"缓存清理任务错误: {e}", exc_info=True)


if __name__ == "__main__":
    import uvicorn
    from server import app
    
    # 添加启动和关闭事件处理
    @app.on_event("startup")
    async def on_startup():
        await startup_tasks()
    
    @app.on_event("shutdown")
    async def on_shutdown():
        await shutdown_tasks()
    
    # 启动服务器
    uvicorn.run(
        app,
        host=get_config('server.host', '127.0.0.1'),
        port=get_config('server.port', 8000),
        reload=get_config('server.reload', False),
        log_level=get_config('server.log_level', 'info')
    )
