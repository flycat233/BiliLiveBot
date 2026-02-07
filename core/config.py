# -*- coding: utf-8 -*-
"""
配置管理模块
统一管理应用配置
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
from cryptography.fernet import Fernet


class ConfigManager:
    """配置管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.config_dir = Path("./data")
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file = self.config_dir / "config.json"
            self.secret_key_file = self.config_dir / ".secret_key"
            
            # 加载或生成加密密钥
            self._load_or_generate_key()
            
            # 加载配置
            self.config = self._load_config()
            self.initialized = True
    
    def _load_or_generate_key(self):
        """加载或生成加密密钥"""
        if self.secret_key_file.exists():
            with open(self.secret_key_file, 'rb') as f:
                self.secret_key = f.read()
        else:
            self.secret_key = Fernet.generate_key()
            with open(self.secret_key_file, 'wb') as f:
                f.write(self.secret_key)
            # 设置文件权限（仅所有者可读写）
            os.chmod(self.secret_key_file, 0o600)
        
        self.cipher = Fernet(self.secret_key)
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置失败: {e}")
                return self._get_default_config()
        return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "server": {
                "host": "127.0.0.1",
                "port": 8000,
                "reload": True,
                "log_level": "info"
            },
            "security": {
                "enable_auth": False,
                "jwt_secret": "",
                "jwt_expire_hours": 24,
                "allowed_origins": ["*"]
            },
            "database": {
                "type": "sqlite",
                "path": "./data/database.db",
                "backup_enabled": True,
                "backup_interval_hours": 24
            },
            "performance": {
                "enable_cache": True,
                "cache_ttl_seconds": 60,
                "max_connections": 100,
                "request_timeout_seconds": 30
            },
            "monitoring": {
                "enable_performance_monitor": True,
                "enable_error_tracking": True,
                "metrics_interval_seconds": 60
            },
            "reconnect": {
                "enable_auto_reconnect": True,
                "max_retries": 5,
                "retry_delay_seconds": 5,
                "exponential_backoff": True
            }
        }
    
    def save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值（支持点号分隔的嵌套键）
        
        Args:
            key: 配置键，如 "server.host"
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        设置配置值（支持点号分隔的嵌套键）
        
        Args:
            key: 配置键，如 "server.host"
            value: 配置值
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        self.save_config()
    
    def encrypt(self, data: str) -> str:
        """
        加密数据
        
        Args:
            data: 要加密的字符串
            
        Returns:
            加密后的字符串
        """
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        解密数据
        
        Args:
            encrypted_data: 加密的字符串
            
        Returns:
            解密后的字符串
        """
        try:
            return self.cipher.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            print(f"解密失败: {e}")
            return ""


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config(key: str, default: Any = None) -> Any:
    """获取配置的便捷函数"""
    return config_manager.get(key, default)


def set_config(key: str, value: Any):
    """设置配置的便捷函数"""
    config_manager.set(key, value)
