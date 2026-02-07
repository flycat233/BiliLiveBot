# -*- coding: utf-8 -*-
"""
B站认证模块
实现扫码登录、Cookie加密存储、匿名模式等功能
"""

import os
import json
import time
import base64
import hashlib
from typing import Dict, Optional
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class BilibiliAuth:
    """B站认证管理器"""
    
    # B站登录相关 API
    QRCODE_GET_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
    QRCODE_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
    
    def __init__(self, data_dir: str = "./data"):
        """
        初始化认证管理器
        
        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.credential_file = self.data_dir / "credential.enc"
        self.cookies = {}
        self.is_anonymous = False
        self.user_info = {}
        
        # 初始化加密器
        self.cipher = self._init_cipher()
        
        # 尝试加载已保存的凭证
        self.load_credential()
    
    def _init_cipher(self) -> Fernet:
        """
        初始化加密器（使用 PBKDF2 + Fernet）
        
        Returns:
            Fernet: 加密器实例
        """
        # 优先从环境变量获取密钥，否则使用基于机器特征的密钥
        import os
        import uuid
        import platform
        
        password = os.environ.get('BILILIVE_ENCRYPTION_KEY', '').encode()
        if not password:
            # 生成基于机器特征的密钥
            machine_id = str(uuid.getnode())  # 获取机器MAC地址
            platform_info = platform.system() + platform.machine()
            password = (machine_id + platform_info + "BililiveRobot_2026").encode()
        
        # 生成随机盐值（基于机器特征）
        salt = os.environ.get('BILILIVE_ENCRYPTION_SALT', '').encode()
        if not salt:
            import hashlib
            salt = hashlib.sha256(str(uuid.getnode()).encode()).digest()[:16]
        
        # 使用 PBKDF2 派生密钥，增加迭代次数以提高安全性
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=200000,  # 增加到200,000次迭代
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        
        return Fernet(key)
    
    async def generate_qrcode(self) -> Dict:
        """
        生成登录二维码

        Returns:
            Dict: {
                "success": bool,
                "qrcode_key": str,
                "qrcode_url": str,
                "qrcode_image": str  # Base64 编码的图片
            }
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(self.QRCODE_GET_URL, headers=headers)

                # 检查 HTTP 状态码
                if response.status_code != 200:
                    return {
                        "success": False,
                        "message": f"HTTP 错误: {response.status_code}"
                    }

                # 检查响应内容
                text = response.text
                if not text or len(text) < 10:
                    return {
                        "success": False,
                        "message": "响应内容为空"
                    }

                # 尝试解析 JSON
                try:
                    data = response.json()
                except Exception as json_error:
                    # 如果 JSON 解析失败，记录实际响应内容
                    print(f"JSON 解析失败，响应内容: {text[:200]}")
                    return {
                        "success": False,
                        "message": f"JSON 解析错误: {str(json_error)}"
                    }

                if data.get("code") == 0:
                    qrcode_data = data["data"]
                    qrcode_url = qrcode_data["url"]
                    qrcode_key = qrcode_data["qrcode_key"]

                    # 生成二维码图片（Base64）
                    qrcode_image = await self._generate_qrcode_image(qrcode_url)

                    return {
                        "success": True,
                        "qrcode_key": qrcode_key,
                        "qrcode_url": qrcode_url,
                        "qrcode_image": qrcode_image
                    }
                else:
                    return {
                        "success": False,
                        "message": data.get("message", "生成二维码失败")
                    }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"网络错误: {str(e)}"
            }
    
    async def _generate_qrcode_image(self, url: str) -> str:
        """
        生成二维码图片（Base64）
        
        Args:
            url: 二维码内容
            
        Returns:
            str: Base64 编码的图片
        """
        try:
            import qrcode
            from io import BytesIO
            
            # 生成二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # 转换为 Base64
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/png;base64,{img_base64}"
        except ImportError:
            # 如果没有安装 qrcode 库，返回一个占位符
            return ""
    
    async def poll_qrcode_status(self, qrcode_key: str) -> Dict:
        """
        轮询二维码状态

        Args:
            qrcode_key: 二维码密钥

        Returns:
            Dict: {
                "success": bool,
                "status": str,  # "pending" | "scanned" | "confirmed" | "expired"
                "message": str,
                "cookies": Dict  # 仅在 confirmed 时返回
            }
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.QRCODE_POLL_URL,
                    params={"qrcode_key": qrcode_key},
                    headers=headers
                )

                # 检查 HTTP 状态码
                if response.status_code != 200:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"HTTP 错误: {response.status_code}"
                    }

                # 尝试解析 JSON
                try:
                    data = response.json()
                except Exception as json_error:
                    print(f"JSON 解析失败，响应内容: {response.text[:200]}")
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"JSON 解析错误: {str(json_error)}"
                    }

                code = data.get("data", {}).get("code")

                # 86101: 未扫描
                # 86090: 已扫描未确认
                # 0: 已确认
                # 86038: 二维码已失效

                if code == 86101:
                    return {
                        "success": True,
                        "status": "pending",
                        "message": "等待扫描"
                    }
                elif code == 86090:
                    return {
                        "success": True,
                        "status": "scanned",
                        "message": "已扫描，等待确认"
                    }
                elif code == 0:
                    # 登录成功，提取 Cookie
                    cookies_dict = {}
                    for cookie in response.cookies.jar:
                        cookies_dict[cookie.name] = cookie.value

                    # 获取用户信息
                    refresh_token = data.get("data", {}).get("refresh_token", "")

                    self.cookies = cookies_dict
                    self.is_anonymous = False

                    # 获取用户信息
                    await self._fetch_user_info()

                    # 设置当前用户信息到用户管理器
                    if self.user_info:
                        from core.user_manager import user_manager
                        user_id = self.user_info.get("mid") or self.user_info.get("uid")
                        user_name = self.user_info.get("uname")
                        if user_id and user_name:
                            user_manager.set_current_user(user_id, user_name)

                    # 保存凭证（在获取用户信息之后）
                    self.save_credential()

                    return {
                        "success": True,
                        "status": "confirmed",
                        "message": "登录成功",
                        "cookies": cookies_dict,
                        "user_info": self.user_info
                    }
                elif code == 86038:
                    return {
                        "success": False,
                        "status": "expired",
                        "message": "二维码已过期"
                    }
                else:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"未知状态码: {code}"
                    }
        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "message": f"网络错误: {str(e)}"
            }
    
    async def _fetch_user_info(self):
        """获取用户信息"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
            }

            async with httpx.AsyncClient(cookies=self.cookies) as client:
                response = await client.get(
                    "https://api.bilibili.com/x/web-interface/nav",
                    headers=headers
                )

                # 检查 HTTP 状态码
                if response.status_code != 200:
                    print(f"获取用户信息失败: HTTP {response.status_code}")
                    return

                # 检查响应内容
                if not response.text or len(response.text) < 10:
                    print("获取用户信息失败: 响应内容为空")
                    return

                # 尝试解析 JSON
                try:
                    data = response.json()
                except Exception as json_error:
                    print(f"获取用户信息失败: JSON 解析错误 - {json_error}")
                    print(f"响应内容: {response.text[:200]}")
                    return

                if data.get("code") == 0:
                    user_data = data["data"]
                    self.user_info = {
                        "uid": user_data.get("mid"),
                        "uname": user_data.get("uname"),
                        "face": user_data.get("face"),
                        "level": user_data.get("level_info", {}).get("current_level", 0),
                        "vip_type": user_data.get("vipType", 0),
                        "login_time": int(time.time())
                    }
                else:
                    print(f"获取用户信息失败: {data.get('message', '未知错误')}")
        except Exception as e:
            print(f"获取用户信息失败: {e}")
    
    def save_credential(self):
        """保存登录凭证（加密存储）"""
        try:
            credential_data = {
                "cookies": self.cookies,
                "user_info": self.user_info,
                "is_anonymous": self.is_anonymous,
                "save_time": int(time.time())
            }
            
            # 序列化为 JSON
            json_data = json.dumps(credential_data, ensure_ascii=False)
            
            # 加密
            encrypted_data = self.cipher.encrypt(json_data.encode())
            
            # 保存到文件
            with open(self.credential_file, "wb") as f:
                f.write(encrypted_data)
            
            # 设置文件权限为仅所有者可读写（在Windows上使用ACL）
            try:
                if platform.system() != 'Windows':
                    os.chmod(self.credential_file, 0o600)
            except:
                pass  # 在某些系统上可能无法设置权限
            
            print("凭证保存成功")
            return True
        except Exception as e:
            print(f"保存凭证失败: {e}")
            return False
    
    def load_credential(self) -> bool:
        """
        加载登录凭证（解密）
        
        Returns:
            bool: 是否加载成功
        """
        try:
            if not self.credential_file.exists():
                return False
            
            # 读取加密数据
            with open(self.credential_file, "rb") as f:
                encrypted_data = f.read()
            
            # 解密
            decrypted_data = self.cipher.decrypt(encrypted_data)
            
            # 解析 JSON
            credential_data = json.loads(decrypted_data.decode())
            
            self.cookies = credential_data.get("cookies", {})
            self.user_info = credential_data.get("user_info", {})
            self.is_anonymous = credential_data.get("is_anonymous", False)
            
            print("凭证加载成功")
            return True
        except Exception as e:
            print(f"加载凭证失败: {e}")
            return False
    
    def set_anonymous(self):
        """切换到匿名模式"""
        self.is_anonymous = True
        self.cookies = {}
        self.user_info = {}
        self.save_credential()
        print("已切换到匿名模式")
    
    def logout(self):
        """退出登录"""
        self.cookies = {}
        self.user_info = {}
        self.is_anonymous = False
        
        # 删除凭证文件
        if self.credential_file.exists():
            self.credential_file.unlink()
        
        print("已退出登录")
    
    def is_logged_in(self) -> bool:
        """
        检查是否已登录
        
        Returns:
            bool: 是否已登录
        """
        return len(self.cookies) > 0 and not self.is_anonymous
    
    def get_cookies_dict(self) -> Dict:
        """
        获取 Cookie 字典
        
        Returns:
            Dict: Cookie 字典
        """
        return self.cookies.copy()
    
    def get_status(self) -> Dict:
        """
        获取登录状态

        Returns:
            Dict: 状态信息
        """
        if self.is_anonymous:
            return {
                "logged_in": False,
                "mode": "anonymous",
                "message": "匿名模式"
            }
        elif self.is_logged_in():
            # 计算凭证有效期（假设 Cookie 有效期为 30 天）
            save_time = self.user_info.get("login_time", 0)
            expire_time = save_time + 30 * 24 * 3600
            remaining_days = max(0, (expire_time - int(time.time())) // 86400)

            # 确保 user_info 有默认值
            user_info = {
                "uid": self.user_info.get("uid", "未知"),
                "uname": self.user_info.get("uname", "未知"),
                "face": self.user_info.get("face", ""),
                "level": self.user_info.get("level", 0),
                "vip_type": self.user_info.get("vip_type", 0),
            }

            return {
                "logged_in": True,
                "mode": "login",
                "user_info": user_info,
                "remaining_days": remaining_days
            }
        else:
            return {
                "logged_in": False,
                "mode": "none",
                "message": "未登录"
            }
