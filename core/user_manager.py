# -*- coding: utf-8 -*-
"""
用户信息管理器
用于存储和管理当前登录用户的信息
"""

class UserManager:
    """用户信息管理器"""
    
    def __init__(self):
        self.current_user_id = None
        self.current_user_name = None
        self.is_logged_in = False
    
    def set_current_user(self, user_id: int, user_name: str):
        """设置当前登录用户信息"""
        self.current_user_id = user_id
        self.current_user_name = user_name
        self.is_logged_in = True
        print(f"[用户管理] 设置当前用户: ID={user_id}, 名称={user_name}")
    
    def get_current_user_id(self) -> int:
        """获取当前登录用户ID"""
        return self.current_user_id
    
    def get_current_user_name(self) -> str:
        """获取当前登录用户名"""
        return self.current_user_name or ""
    
    def is_current_user(self, user_id: int, user_name: str = None) -> bool:
        """检查是否为当前登录用户"""
        if not self.is_logged_in or self.current_user_id is None:
            return False
        
        # 优先使用ID判断
        if user_id and self.current_user_id == user_id:
            return True
        
        # 如果ID匹配不上，再尝试用户名匹配
        if user_name and self.current_user_name and self.current_user_name == user_name:
            return True
        
        return False
    
    def logout(self):
        """登出"""
        self.current_user_id = None
        self.current_user_name = None
        self.is_logged_in = False
        print("[用户管理] 用户已登出")


# 全局单例实例
user_manager = UserManager()