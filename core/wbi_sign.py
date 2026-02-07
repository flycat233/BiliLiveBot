# -*- coding: utf-8 -*-
"""
B站 WBI 签名模块
用于 B站 Web API 接口鉴权
"""

import hashlib
import time
import urllib.parse
from functools import reduce
from typing import Dict, Tuple, Optional

import httpx


# WBI 混合密钥编码表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]


class WBISigner:
    """WBI 签名器"""
    
    def __init__(self, cookies: Optional[Dict] = None):
        self._img_key: Optional[str] = None
        self._sub_key: Optional[str] = None
        self._mixin_key: Optional[str] = None
        self._last_update: float = 0
        self._nav_url = "https://api.bilibili.com/x/web-interface/nav"
        self._cookies = cookies or {}
    
    def set_cookies(self, cookies: Dict):
        """设置 Cookie"""
        self._cookies = cookies
        # 清除缓存，强制重新获取密钥
        self._img_key = None
        self._sub_key = None
    
    async def get_wbi_keys(self) -> Tuple[str, str]:
        """
        获取 WBI 签名密钥

        Returns:
            (img_key, sub_key)
        """
        # 检查是否需要更新密钥（24小时更新一次）
        current_time = time.time()
        if self._img_key and self._sub_key and (current_time - self._last_update) < 86400:
            return self._img_key, self._sub_key

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
            }

            async with httpx.AsyncClient(cookies=self._cookies) as client:
                response = await client.get(self._nav_url, headers=headers)

                # 检查 HTTP 状态码
                if response.status_code != 200:
                    print(f"获取 WBI 密钥失败: HTTP {response.status_code}")
                    if self._img_key and self._sub_key:
                        return self._img_key, self._sub_key
                    raise Exception(f"HTTP {response.status_code}")

                # 检查响应内容
                if not response.text or len(response.text) < 10:
                    print("获取 WBI 密钥失败: 响应内容为空")
                    if self._img_key and self._sub_key:
                        return self._img_key, self._sub_key
                    raise Exception("响应内容为空")

                # 尝试解析 JSON
                try:
                    data = response.json()
                except Exception as json_error:
                    print(f"获取 WBI 密钥失败: JSON 解析错误 - {json_error}")
                    print(f"响应内容: {response.text[:200]}")
                    if self._img_key and self._sub_key:
                        return self._img_key, self._sub_key
                    raise

                # 检查 API 返回状态
                if data.get("code") != 0:
                    print(f"获取 WBI 密钥失败: API 返回错误 - {data.get('message')}")
                    if self._img_key and self._sub_key:
                        return self._img_key, self._sub_key
                    raise Exception(f"API 错误: {data.get('message')}")

                # 提取 wbi_img
                wbi_img = data.get("data", {}).get("wbi_img", {})
                if not wbi_img or not wbi_img.get("img_url") or not wbi_img.get("sub_url"):
                    print("获取 WBI 密钥失败: wbi_img 数据缺失")
                    if self._img_key and self._sub_key:
                        return self._img_key, self._sub_key
                    raise Exception("wbi_img 数据缺失")

                img_url = wbi_img["img_url"]
                sub_url = wbi_img["sub_url"]

                # 从 URL 中提取文件名作为密钥
                img_key = img_url.rsplit("/", 1)[1].split(".")[0]
                sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]

                self._img_key = img_key
                self._sub_key = sub_key
                self._last_update = current_time

                print(f"WBI 密钥更新成功: img_key={img_key[:8]}..., sub_key={sub_key[:8]}...")

                return img_key, sub_key

        except Exception as e:
            print(f"获取 WBI 密钥失败: {e}")
            # 如果失败，返回之前的密钥（如果有）
            if self._img_key and self._sub_key:
                return self._img_key, self._sub_key
            raise
    
    def _get_mixin_key(self, orig_key: str) -> str:
        """
        对 imgKey 和 subKey 进行字符顺序打乱编码
        
        Args:
            orig_key: 拼接后的原始密钥
            
        Returns:
            混合密钥（32位）
        """
        return reduce(lambda s, i: s + orig_key[i], MIXIN_KEY_ENC_TAB, "")[:32]
    
    async def sign_params(self, params: Dict) -> Dict:
        """
        为请求参数进行 WBI 签名
        
        Args:
            params: 原始请求参数
            
        Returns:
            签名后的参数（包含 w_rid 和 wts）
        """
        # 获取密钥
        img_key, sub_key = await self.get_wbi_keys()
        
        # 生成混合密钥
        mixin_key = self._get_mixin_key(img_key + sub_key)
        
        # 添加时间戳
        curr_time = int(time.time())
        params["wts"] = curr_time
        
        # 按照 key 重排参数
        params = dict(sorted(params.items()))
        
        # 过滤 value 中的 "!'()*" 字符
        params = {
            k: "".join(filter(lambda chr: chr not in "!()*", str(v)))
            for k, v in params.items()
        }
        
        # 序列化参数
        query = urllib.parse.urlencode(params)
        
        # 计算 w_rid
        wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()
        params["w_rid"] = wbi_sign
        
        return params


# 全局签名器实例
_wbi_signer = WBISigner()


def set_wbi_cookies(cookies: Dict):
    """
    设置 WBI 签名器的 Cookie
    
    Args:
        cookies: Cookie 字典
    """
    _wbi_signer.set_cookies(cookies)


async def sign_params(params: Dict, cookies: Optional[Dict] = None) -> Dict:
    """
    为请求参数进行 WBI 签名（便捷函数）
    
    Args:
        params: 原始请求参数
        cookies: 可选的 Cookie 字典
        
    Returns:
        签名后的参数（包含 w_rid 和 wts）
    """
    # 如果提供了 cookies，使用临时签名器
    if cookies:
        temp_signer = WBISigner(cookies=cookies)
        return await temp_signer.sign_params(params)
    
    return await _wbi_signer.sign_params(params)