# -*- coding: utf-8 -*-
"""
增强的插件基类
添加生命周期管理和更多功能
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import asyncio

from core.plugin_system import PluginBase
from core.logger import get_logger
from core.performance import performance_monitor

logger = get_logger("plugin_enhanced")


class PluginBaseEnhanced(PluginBase):
    """增强版插件基类"""
    
    # 插件依赖（子类可选定义）
    dependencies: List[str] = []
    
    # 插件优先级（数字越小优先级越高）
    priority: int = 100
    
    def __init__(self):
        super().__init__()
        self.initialized = False
        self.logger = get_logger(f"plugin.{self.name}")
        # bot_messages 已在父类中初始化
    
    async def on_init(self):
        """
        插件初始化钩子
        在插件加载时调用，用于初始化资源
        """
        self.logger.info(f"插件 {self.name} 初始化")
        self.initialized = True
    
    async def on_destroy(self):
        """
        插件销毁钩子
        在插件卸载时调用，用于清理资源
        """
        self.logger.info(f"插件 {self.name} 销毁")
        self.initialized = False
    
    async def on_enable(self):
        """
        插件启用钩子
        在插件被启用时调用
        """
        self.logger.info(f"插件 {self.name} 已启用")
    
    async def on_disable(self):
        """
        插件禁用钩子
        在插件被禁用时调用
        """
        self.logger.info(f"插件 {self.name} 已禁用")
    
    def get_dependencies(self) -> List[str]:
        """
        获取插件依赖列表
        
        Returns:
            依赖的插件名称列表
        """
        return self.dependencies
    
    def get_priority(self) -> int:
        """
        获取插件优先级
        
        Returns:
            优先级数值
        """
        return self.priority
    
    async def _execute_with_monitoring(self, func, *args, **kwargs):
        """
        执行函数并监控性能
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果
        """
        import time
        start_time = time.time()
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            execution_time = time.time() - start_time
            performance_monitor.record_plugin_execution(self.name, execution_time)
            
            if execution_time > 0.1:  # 超过100ms记录警告
                self.logger.warning(f"插件执行时间过长: {execution_time:.3f}秒")
            
            return result
        
        except Exception as e:
            self.logger.error(f"插件执行错误: {e}", exc_info=True)
            performance_monitor.record_error()
            raise
    
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """
        处理弹幕事件（带性能监控）
        
        Args:
            data: 弹幕数据
            
        Returns:
            处理后的数据
        """
        return await self._execute_with_monitoring(self._on_danmaku_impl, data)
    
    async def _on_danmaku_impl(self, data: dict) -> Optional[dict]:
        """
        弹幕处理实现（子类重写此方法）
        
        Args:
            data: 弹幕数据
            
        Returns:
            处理后的数据
        """
        return data
    
    async def on_gift(self, data: dict) -> Optional[dict]:
        """处理礼物事件（带性能监控）"""
        return await self._execute_with_monitoring(self._on_gift_impl, data)
    
    async def _on_gift_impl(self, data: dict) -> Optional[dict]:
        """礼物处理实现（子类重写此方法）"""
        return data
    
    async def on_guard(self, data: dict) -> Optional[dict]:
        """处理上舰事件（带性能监控）"""
        return await self._execute_with_monitoring(self._on_guard_impl, data)
    
    async def _on_guard_impl(self, data: dict) -> Optional[dict]:
        """上舰处理实现（子类重写此方法）"""
        return data
    
    async def on_superchat(self, data: dict) -> Optional[dict]:
        """处理SC事件（带性能监控）"""
        return await self._execute_with_monitoring(self._on_superchat_impl, data)
    
    async def _on_superchat_impl(self, data: dict) -> Optional[dict]:
        """SC处理实现（子类重写此方法）"""
        return data
    
    async def on_interact(self, data: dict) -> Optional[dict]:
        """处理互动事件（带性能监控）"""
        return await self._execute_with_monitoring(self._on_interact_impl, data)
    
    async def _on_interact_impl(self, data: dict) -> Optional[dict]:
        """互动处理实现（子类重写此方法）"""
        return data
    
    async def on_online(self, data: dict) -> Optional[dict]:
        """处理在线人数更新事件（带性能监控）"""
        return await self._execute_with_monitoring(self._on_online_impl, data)
    
    async def _on_online_impl(self, data: dict) -> Optional[dict]:
        """在线人数处理实现（子类重写此方法）"""
        return data
    
    def validate_config(self, config: Dict) -> bool:
        """
        验证配置是否有效
        
        Args:
            config: 配置字典
            
        Returns:
            是否有效
        """
        # 子类可以重写此方法进行配置验证
        return True
    
    def get_status(self) -> Dict:
        """
        获取插件状态
        
        Returns:
            状态字典
        """
        return {
            'name': self.name,
            'enabled': self.enabled,
            'initialized': self.initialized,
            'priority': self.priority,
            'dependencies': self.dependencies
        }
