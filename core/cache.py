# -*- coding: utf-8 -*-
"""
缓存模块
提供内存缓存功能
"""

import time
from typing import Any, Optional, Dict
from collections import OrderedDict
from threading import Lock

from core.logger import get_logger

logger = get_logger("cache")


class CacheItem:
    """缓存项"""
    
    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.expire_time = time.time() + ttl if ttl > 0 else None
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expire_time is None:
            return False
        return time.time() > self.expire_time


class Cache:
    """缓存管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 60):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存项数量
            default_ttl: 默认过期时间（秒），0表示永不过期
        """
        if not hasattr(self, 'initialized'):
            self.max_size = max_size
            self.default_ttl = default_ttl
            self.cache: OrderedDict[str, CacheItem] = OrderedDict()
            self.lock = Lock()
            self.hits = 0
            self.misses = 0
            self.initialized = True
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            default: 默认值
            
        Returns:
            缓存值或默认值
        """
        with self.lock:
            if key in self.cache:
                item = self.cache[key]
                
                # 检查是否过期
                if item.is_expired():
                    del self.cache[key]
                    self.misses += 1
                    logger.debug(f"缓存过期: {key}")
                    return default
                
                # 移到末尾（LRU）
                self.cache.move_to_end(key)
                self.hits += 1
                logger.debug(f"缓存命中: {key}")
                return item.value
            
            self.misses += 1
            logger.debug(f"缓存未命中: {key}")
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None使用默认值
        """
        with self.lock:
            if ttl is None:
                ttl = self.default_ttl
            
            # 如果已存在，先删除
            if key in self.cache:
                del self.cache[key]
            
            # 如果超过最大大小，删除最旧的项
            while len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                logger.debug(f"缓存已满，删除最旧项: {oldest_key}")
            
            # 添加新项
            self.cache[key] = CacheItem(value, ttl)
            logger.debug(f"缓存设置: {key}, TTL={ttl}秒")
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                logger.debug(f"缓存删除: {key}")
                return True
            return False
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            logger.info("缓存已清空")
    
    def cleanup_expired(self):
        """清理过期项"""
        with self.lock:
            expired_keys = []
            for key, item in self.cache.items():
                if item.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                logger.info(f"清理了 {len(expired_keys)} 个过期缓存项")
    
    def get_stats(self) -> Dict:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': round(hit_rate, 2),
                'total_requests': total_requests
            }
    
    def exists(self, key: str) -> bool:
        """
        检查键是否存在且未过期
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        with self.lock:
            if key not in self.cache:
                return False
            
            item = self.cache[key]
            if item.is_expired():
                del self.cache[key]
                return False
            
            return True


# 全局缓存实例
cache = Cache()


# 装饰器：缓存函数结果
def cached(ttl: int = 60, key_prefix: str = ""):
    """
    缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 缓存键前缀
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 执行函数
            result = await func(*args, **kwargs)
            
            # 存入缓存
            cache.set(cache_key, result, ttl)
            
            return result
        
        def sync_wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            cache.set(cache_key, result, ttl)
            
            return result
        
        # 判断是否是异步函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
