# -*- coding: utf-8 -*-
"""
插件系统模块
实现插件动态加载、事件分发、配置管理等功能
"""

import os
import json
import importlib
import importlib.util
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path


class PluginBase(ABC):
    """插件基类"""
    
    # 插件元信息（子类必须定义）
    name: str = "未命名插件"
    description: str = "插件描述"
    version: str = "1.0.0"
    author: str = "匿名"
    
    # 插件配置模板（子类可选定义）
    config_schema: List[Dict] = []
    
    def __init__(self):
        """初始化插件"""
        self.enabled = True
        self.config = {}
        self.bot_messages = set()  # 存储机器人发送的消息ID
        self.load_config()

        # 注意：初始化钩子不在此处调用，而是在插件管理器加载插件时调用
        # 避免在 __init__ 中创建 asyncio 任务导致事件循环问题
    
    def load_config(self):
        """加载插件配置"""
        config_file = Path(f"./data/plugins/{self.name}_config.json")
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"加载插件 {self.name} 配置失败: {e}")
    
    def save_config(self):
        """保存插件配置"""
        config_dir = Path("./data/plugins")
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = config_dir / f"{self.name}_config.json"
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存插件 {self.name} 配置失败: {e}")
    
    def update_config(self, new_config: Dict):
        """更新插件配置"""
        self.config.update(new_config)
        self.save_config()
    
    def is_bot_message(self, data: dict) -> bool:
        """
        检查是否是机器人自己发送的消息
        
        Args:
            data: 弹幕数据
            
        Returns:
            bool: 是否是机器人消息
        """
        # 检查消息ID是否在机器人消息集合中
        msg_id = data.get('msg_id') or data.get('id')
        if msg_id and msg_id in self.bot_messages:
            return True
        
        # 检查用户名是否是机器人自己
        # 这里可以根据实际情况添加更多判断逻辑
        return False
    
    def mark_as_bot_message(self, msg_id: str):
        """
        标记消息为机器人消息
        
        Args:
            msg_id: 消息ID
        """
        self.bot_messages.add(msg_id)
        
        # 限制集合大小，避免内存泄漏
        if len(self.bot_messages) > 1000:
            # 移除最旧的500个
            self.bot_messages = set(list(self.bot_messages)[500:])
    
    @abstractmethod
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """
        处理弹幕事件
        
        Args:
            data: 弹幕数据
            
        Returns:
            Optional[dict]: 处理后的数据（可以修改或返回 None 表示不修改）
        """
        pass
    
    async def on_gift(self, data: dict) -> Optional[dict]:
        """处理礼物事件"""
        return data
    
    async def on_guard(self, data: dict) -> Optional[dict]:
        """处理上舰事件"""
        return data
    
    async def on_superchat(self, data: dict) -> Optional[dict]:
        """处理 SC 事件"""
        return data
    
    async def on_interact(self, data: dict) -> Optional[dict]:
        """处理互动事件"""
        return data
    
    async def on_online(self, data: dict) -> Optional[dict]:
        """处理在线人数更新事件"""
        return data

    # ==================== 生命周期钩子 ====================

    async def on_init(self):
        """
        插件初始化钩子
        在插件加载时调用，可用于初始化资源、连接数据库等
        """
        pass

    async def on_destroy(self):
        """
        插件销毁钩子
        在插件卸载时调用，可用于清理资源、关闭连接等
        """
        pass

    async def on_enable(self):
        """
        插件启用钩子
        在插件启用时调用
        """
        pass

    async def on_disable(self):
        """
        插件禁用钩子
        在插件禁用时调用
        """
        pass

    def get_info(self) -> Dict:
        """获取插件信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "enabled": self.enabled,
            "config_schema": self.config_schema,
            "config": self.config
        }


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugin_dir: str = "./plugins"):
        """
        初始化插件管理器
        
        Args:
            plugin_dir: 插件目录
        """
        self.plugin_dir = Path(plugin_dir)
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        
        self.plugins: Dict[str, PluginBase] = {}
        self.plugin_states: Dict[str, bool] = {}  # 插件启用状态
        
        # 加载插件状态
        self._load_plugin_states()
    
    def _load_plugin_states(self):
        """加载插件启用状态"""
        state_file = Path("./data/plugin_states.json")
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    self.plugin_states = json.load(f)
            except Exception as e:
                print(f"加载插件状态失败: {e}")
    
    def _save_plugin_states(self):
        """保存插件启用状态"""
        state_file = Path("./data/plugin_states.json")
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(self.plugin_states, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存插件状态失败: {e}")
    
    def discover_plugins(self) -> List[str]:
        """
        发现所有插件
        
        Returns:
            List[str]: 插件文件名列表
        """
        plugin_files = []
        
        for file in self.plugin_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            plugin_files.append(file.stem)
        
        return plugin_files
    
    def load_plugin(self, plugin_name: str) -> bool:
        """
        加载单个插件

        Args:
            plugin_name: 插件名称（文件名，不含 .py）

        Returns:
            bool: 是否加载成功
        """
        try:
            # 构建插件文件路径
            plugin_file = self.plugin_dir / f"{plugin_name}.py"

            if not plugin_file.exists():
                print(f"插件文件不存在: {plugin_file}")
                return False

            # 动态导入模块
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 查找插件类（继承自 PluginBase 或 PluginBaseEnhanced）
            plugin_class = None
            try:
                # 尝试导入 PluginBaseEnhanced
                from core.plugin_base import PluginBaseEnhanced

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        (issubclass(attr, PluginBase) or issubclass(attr, PluginBaseEnhanced)) and
                        attr is not PluginBase and attr is not PluginBaseEnhanced):
                        plugin_class = attr
                        break
            except ImportError:
                # 如果 PluginBaseEnhanced 不存在，只检查 PluginBase
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        issubclass(attr, PluginBase) and
                        attr is not PluginBase):
                        plugin_class = attr
                        break

            if plugin_class is None:
                print(f"插件 {plugin_name} 中未找到插件类")
                return False

            # 实例化插件
            plugin_instance = plugin_class()

            # 设置插件启用状态
            if plugin_instance.name in self.plugin_states:
                plugin_instance.enabled = self.plugin_states[plugin_instance.name]

            self.plugins[plugin_instance.name] = plugin_instance

            # 调用初始化钩子
            try:
                if asyncio.iscoroutinefunction(plugin_instance.on_init):
                    # 如果是异步方法，在事件循环中执行
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(plugin_instance.on_init())
                        else:
                            # 如果事件循环未运行，忽略（将在 __init__ 中调用）
                            pass
                    except RuntimeError:
                        # 如果没有事件循环，忽略
                        pass
                else:
                    plugin_instance.on_init()
            except Exception as e:
                print(f"调用插件 {plugin_instance.name} 初始化钩子失败: {e}")

            print(f"插件 {plugin_instance.name} 加载成功")
            return True
        except Exception as e:
            print(f"加载插件 {plugin_name} 失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_all_plugins(self):
        """加载所有插件"""
        plugin_files = self.discover_plugins()
        
        for plugin_file in plugin_files:
            self.load_plugin(plugin_file)
        
        print(f"共加载 {len(self.plugins)} 个插件")
    
    def get_plugin_list(self) -> List[Dict]:
        """
        获取插件列表
        
        Returns:
            List[Dict]: 插件信息列表
        """
        return [plugin.get_info() for plugin in self.plugins.values()]
    
    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """
        获取插件实例
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Optional[PluginBase]: 插件实例
        """
        return self.plugins.get(plugin_name)
    
    def update_plugin_config(self, plugin_name: str, config: Dict) -> bool:
        """
        更新插件配置
        
        Args:
            plugin_name: 插件名称
            config: 新配置
            
        Returns:
            bool: 是否更新成功
        """
        plugin = self.get_plugin(plugin_name)
        if plugin:
            plugin.update_config(config)
            return True
        return False
    
    def toggle_plugin(self, plugin_name: str, enabled: bool) -> bool:
        """
        启用/禁用插件

        Args:
            plugin_name: 插件名称
            enabled: 是否启用

        Returns:
            bool: 是否操作成功
        """
        plugin = self.get_plugin(plugin_name)
        if plugin:
            plugin.enabled = enabled
            self.plugin_states[plugin_name] = enabled
            self._save_plugin_states()

            # 调用生命周期钩子
            try:
                if enabled:
                    if asyncio.iscoroutinefunction(plugin.on_enable):
                        asyncio.create_task(plugin.on_enable())
                    else:
                        plugin.on_enable()
                else:
                    if asyncio.iscoroutinefunction(plugin.on_disable):
                        asyncio.create_task(plugin.on_disable())
                    else:
                        plugin.on_disable()
            except Exception as e:
                print(f"调用插件 {plugin_name} 生命周期钩子失败: {e}")

            print(f"插件 {plugin_name} 已{'启用' if enabled else '禁用'}")
            return True
        return False
    
    async def process_event(self, event_type: str, data: dict) -> dict:
        """
        处理事件（分发到所有启用的插件）
        
        Args:
            event_type: 事件类型（danmaku, gift, guard, superchat, interact, online）
            data: 事件数据
            
        Returns:
            dict: 处理后的数据
        """
        result_data = data.copy()
        
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            
            try:
                # 根据事件类型调用对应的处理方法
                if event_type == "danmaku":
                    processed = await plugin.on_danmaku(result_data)
                elif event_type == "gift":
                    processed = await plugin.on_gift(result_data)
                elif event_type == "guard":
                    processed = await plugin.on_guard(result_data)
                elif event_type == "superchat":
                    processed = await plugin.on_superchat(result_data)
                elif event_type == "interact":
                    processed = await plugin.on_interact(result_data)
                elif event_type == "online":
                    processed = await plugin.on_online(result_data)
                else:
                    processed = result_data
                
                # 如果插件返回了处理后的数据，则更新
                if processed is not None:
                    result_data = processed
            except Exception as e:
                print(f"插件 {plugin.name} 处理事件 {event_type} 失败: {e}")
        
        return result_data
    
    def set_websocket_manager(self, ws_manager):
        """
        设置WebSocket管理器，并将其传递给所有插件
        
        Args:
            ws_manager: WebSocket管理器实例
        """
        for plugin in self.plugins.values():
            # 检查插件是否有set_websocket_manager方法
            if hasattr(plugin, 'set_websocket_manager'):
                try:
                    plugin.set_websocket_manager(ws_manager)
                    print(f"已为插件 {plugin.name} 设置WebSocket管理器")
                except Exception as e:
                    print(f"为插件 {plugin.name} 设置WebSocket管理器失败: {e}")
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """
        重新加载插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            bool: 是否重新加载成功
        """
        # 查找对应的文件名
        plugin_file_name = None
        for file in self.plugin_dir.glob("*.py"):
            if file.stem == plugin_name or file.stem in self.plugins:
                plugin = self.plugins.get(file.stem)
                if plugin and plugin.name == plugin_name:
                    plugin_file_name = file.stem
                    break
        
        if plugin_file_name is None:
            return False
        
        # 移除旧插件
        if plugin_name in self.plugins:
            del self.plugins[plugin_name]
        
        # 重新加载
        return self.load_plugin(plugin_file_name)
