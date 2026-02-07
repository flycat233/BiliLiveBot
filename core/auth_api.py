# -*- coding: utf-8 -*-
"""
API认证模块
提供JWT认证功能
"""

import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.logger import get_logger
from core.config import config_manager

logger = get_logger("auth_api")

# HTTP Bearer认证
security = HTTPBearer()


class APIAuth:
    """API认证管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            # 获取或生成JWT密钥
            self.jwt_secret = config_manager.get('security.jwt_secret')
            if not self.jwt_secret:
                self.jwt_secret = secrets.token_urlsafe(32)
                config_manager.set('security.jwt_secret', self.jwt_secret)
            
            self.jwt_algorithm = 'HS256'
            self.jwt_expire_hours = config_manager.get('security.jwt_expire_hours', 24)
            self.initialized = True
    
    def generate_token(self, user_id: str, extra_data: Optional[Dict] = None) -> str:
        """
        生成JWT令牌
        
        Args:
            user_id: 用户ID
            extra_data: 额外数据
            
        Returns:
            JWT令牌字符串
        """
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(hours=self.jwt_expire_hours),
            'iat': datetime.utcnow()
        }
        
        if extra_data:
            payload.update(extra_data)
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        logger.info(f"生成令牌: user_id={user_id}")
        
        return token
    
    def verify_token(self, token: str) -> Dict:
        """
        验证JWT令牌
        
        Args:
            token: JWT令牌字符串
            
        Returns:
            解码后的payload
            
        Raises:
            HTTPException: 令牌无效或过期
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("令牌已过期")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已过期",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"无效的令牌: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的令牌",
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    def get_current_user(self, 
                        credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict:
        """
        获取当前用户（用于FastAPI依赖注入）
        
        Args:
            credentials: HTTP认证凭据
            
        Returns:
            用户信息字典
        """
        token = credentials.credentials
        payload = self.verify_token(token)
        return payload
    
    def generate_api_key(self) -> str:
        """
        生成API密钥
        
        Returns:
            API密钥字符串
        """
        api_key = secrets.token_urlsafe(32)
        logger.info("生成新的API密钥")
        return api_key
    
    def verify_api_key(self, api_key: str) -> bool:
        """
        验证API密钥
        
        Args:
            api_key: API密钥
            
        Returns:
            是否有效
        """
        # 这里可以从数据库或配置中验证API密钥
        # 简单实现：从配置中获取有效的API密钥列表
        valid_keys = config_manager.get('security.api_keys', [])
        return api_key in valid_keys


# 全局API认证实例
api_auth = APIAuth()


# FastAPI依赖函数
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict:
    """获取当前用户的依赖函数"""
    return api_auth.get_current_user(credentials)


async def verify_api_key_dependency(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> bool:
    """验证API密钥的依赖函数"""
    api_key = credentials.credentials
    if not api_auth.verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的API密钥",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return True
