# -*- coding: utf-8 -*-
"""
性能监控模块
监控系统性能指标
"""

import asyncio
import psutil
import time
from datetime import datetime
from typing import Dict, List
from collections import deque

from core.logger import get_logger
from core.database import db

logger = get_logger("performance")


class PerformanceMonitor:
    """性能监控器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.metrics = {
                'cpu_percent': deque(maxlen=60),
                'memory_percent': deque(maxlen=60),
                'danmaku_processing_time': deque(maxlen=100),
                'plugin_execution_time': {},
                'websocket_connections': 0,
                'danmaku_count': 0,
                'error_count': 0
            }
            self.start_time = time.time()
            self.monitoring_task = None
            self.initialized = True
    
    async def start_monitoring(self, interval: int = 60):
        """启动性能监控"""
        logger.info("启动性能监控")
        
        async def monitor_loop():
            while True:
                try:
                    await self.collect_metrics()
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"性能监控错误: {e}")
                    await asyncio.sleep(interval)
        
        self.monitoring_task = asyncio.create_task(monitor_loop())
    
    async def stop_monitoring(self):
        """停止性能监控"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("性能监控已停止")
    
    async def collect_metrics(self):
        """收集性能指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            self.metrics['cpu_percent'].append(cpu_percent)
            db.save_metric('cpu_percent', cpu_percent, '%')
            
            # 内存使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            self.metrics['memory_percent'].append(memory_percent)
            db.save_metric('memory_percent', memory_percent, '%')
            
            # 运行时间
            uptime = time.time() - self.start_time
            db.save_metric('uptime', uptime, 'seconds')
            
            # WebSocket连接数
            db.save_metric('websocket_connections', 
                          self.metrics['websocket_connections'], 'count')
            
            # 弹幕处理数量
            db.save_metric('danmaku_count', 
                          self.metrics['danmaku_count'], 'count')
            
            # 错误数量
            db.save_metric('error_count', 
                          self.metrics['error_count'], 'count')
            
            logger.debug(f"性能指标: CPU={cpu_percent:.1f}%, "
                        f"内存={memory_percent:.1f}%, "
                        f"弹幕={self.metrics['danmaku_count']}")
        
        except Exception as e:
            logger.error(f"收集性能指标失败: {e}")
    
    def record_danmaku_processing(self, processing_time: float):
        """记录弹幕处理时间"""
        self.metrics['danmaku_processing_time'].append(processing_time)
        self.metrics['danmaku_count'] += 1
    
    def record_plugin_execution(self, plugin_name: str, execution_time: float):
        """记录插件执行时间"""
        if plugin_name not in self.metrics['plugin_execution_time']:
            self.metrics['plugin_execution_time'][plugin_name] = deque(maxlen=100)
        
        self.metrics['plugin_execution_time'][plugin_name].append(execution_time)
    
    def record_error(self):
        """记录错误"""
        self.metrics['error_count'] += 1
    
    def set_websocket_connections(self, count: int):
        """设置WebSocket连接数"""
        self.metrics['websocket_connections'] = count
    
    def get_current_metrics(self) -> Dict:
        """获取当前性能指标"""
        cpu_avg = sum(self.metrics['cpu_percent']) / len(self.metrics['cpu_percent']) \
                  if self.metrics['cpu_percent'] else 0
        
        memory_avg = sum(self.metrics['memory_percent']) / len(self.metrics['memory_percent']) \
                     if self.metrics['memory_percent'] else 0
        
        danmaku_avg_time = sum(self.metrics['danmaku_processing_time']) / \
                          len(self.metrics['danmaku_processing_time']) \
                          if self.metrics['danmaku_processing_time'] else 0
        
        plugin_times = {}
        for plugin_name, times in self.metrics['plugin_execution_time'].items():
            if times:
                plugin_times[plugin_name] = {
                    'avg': sum(times) / len(times),
                    'max': max(times),
                    'min': min(times)
                }
        
        return {
            'cpu_percent': round(cpu_avg, 2),
            'memory_percent': round(memory_avg, 2),
            'danmaku_processing_time_ms': round(danmaku_avg_time * 1000, 2),
            'plugin_execution_times': plugin_times,
            'websocket_connections': self.metrics['websocket_connections'],
            'danmaku_count': self.metrics['danmaku_count'],
            'error_count': self.metrics['error_count'],
            'uptime_seconds': round(time.time() - self.start_time, 2)
        }
    
    def get_health_status(self) -> Dict:
        """获取健康状态"""
        metrics = self.get_current_metrics()
        
        # 判断健康状态
        status = "healthy"
        issues = []
        
        if metrics['cpu_percent'] > 80:
            status = "warning"
            issues.append("CPU使用率过高")
        
        if metrics['memory_percent'] > 80:
            status = "warning"
            issues.append("内存使用率过高")
        
        if metrics['danmaku_processing_time_ms'] > 100:
            status = "warning"
            issues.append("弹幕处理延迟过高")
        
        if metrics['error_count'] > 10:
            status = "error"
            issues.append("错误数量过多")
        
        return {
            'status': status,
            'issues': issues,
            'metrics': metrics,
            'timestamp': datetime.now().isoformat()
        }


# 全局性能监控器实例
performance_monitor = PerformanceMonitor()
