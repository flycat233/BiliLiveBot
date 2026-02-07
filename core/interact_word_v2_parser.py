#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INTERACT_WORD_V2 Protobuf解析器
使用pure-protobuf库解析B站直播的用户进入事件
"""

import base64
import json
from typing import Dict, Optional
from dataclasses import dataclass

try:
    from pure_protobuf import types
    from pure_protobuf.dataclasses_ import message, field
    PURE_PROTOBUF_AVAILABLE = True
except ImportError:
    print("警告: pure-protobuf 未安装，将使用简化解析器")
    PURE_PROTOBUF_AVAILABLE = False


if PURE_PROTOBUF_AVAILABLE:
    @message
    @dataclass
    class UserInfo:
        """用户信息"""
        face: Optional[str] = field(1, default=None)
        name: Optional[str] = field(2, default=None)
    
    @message
    @dataclass
    class InteractWordV2:
        """INTERACT_WORD_V2 protobuf消息"""
        uid: Optional[int] = field(1, default=None)
        uname: Optional[str] = field(2, default=None)
        uinfo: Optional[UserInfo] = field(3, default=None)
        timestamp: Optional[int] = field(6, default=None)
        msg_type: Optional[int] = field(5, default=None)


class InteractWordV2Parser:
    """INTERACT_WORD_V2解析器"""
    
    def __init__(self):
        self.use_pure_protobuf = PURE_PROTOBUF_AVAILABLE
        if not self.use_pure_protobuf:
            print("使用简化protobuf解析器")
    
    def parse(self, pb_data: str) -> Optional[Dict]:
        """
        解析INTERACT_WORD_V2的protobuf数据
        
        Args:
            pb_data: base64编码的protobuf字符串
            
        Returns:
            解析后的数据字典，包含uid、uname、msg_type、timestamp等字段
        """
        try:
            # 解码base64
            pb_bytes = base64.b64decode(pb_data)
            
            if self.use_pure_protobuf:
                return self._parse_with_pure_protobuf(pb_bytes)
            else:
                return self._parse_simple(pb_bytes)
                
        except Exception as e:
            print(f"解析INTERACT_WORD_V2失败: {e}")
            return None
    
    def _parse_with_pure_protobuf(self, pb_bytes: bytes) -> Optional[Dict]:
        """使用pure-protobuf库解析"""
        try:
            # 解析protobuf消息
            interact_msg = InteractWordV2.read_from_bytes(pb_bytes)
            
            # 提取数据
            result = {
                "uid": interact_msg.uid or 0,
                "uname": interact_msg.uname or "",
                "msg_type": interact_msg.msg_type or 1,
                "timestamp": interact_msg.timestamp or 0
            }
            
            # 从uinfo中获取更多信息
            if interact_msg.uinfo:
                if interact_msg.uinfo.name and not result["uname"]:
                    result["uname"] = interact_msg.uinfo.name
                if interact_msg.uinfo.face:
                    result["face"] = interact_msg.uinfo.face
            
            return result
            
        except Exception as e:
            print(f"pure-protobuf解析失败: {e}")
            # 降级到简化解析器
            return self._parse_simple(pb_bytes)
    
    def _parse_simple(self, pb_bytes: bytes) -> Optional[Dict]:
        """简化的protobuf解析器（不依赖外部库）"""
        try:
            result = {}
            i = 0
            
            while i < len(pb_bytes):
                if i >= len(pb_bytes):
                    break
                
                # 读取字段号和wire type
                field_info = pb_bytes[i]
                i += 1
                
                field_num = field_info >> 3
                wire_type = field_info & 0x07
                
                if wire_type == 0:  # varint
                    value = 0
                    shift = 0
                    while i < len(pb_bytes):
                        byte_val = pb_bytes[i]
                        i += 1
                        value |= (byte_val & 0x7F) << shift
                        if not (byte_val & 0x80):
                            break
                        shift += 7
                        if shift > 63:
                            break
                    
                    # 字段映射（基于实际测试和blivedm源码）
                    if field_num == 1:  # uid
                        result["uid"] = value
                    elif field_num == 5:  # msg_type
                        result["msg_type"] = value
                    elif field_num == 6:  # timestamp
                        result["timestamp"] = value
                        
                elif wire_type == 2:  # length-delimited (string or nested message)
                    # 读取长度
                    length = 0
                    shift = 0
                    while i < len(pb_bytes):
                        byte_val = pb_bytes[i]
                        i += 1
                        length |= (byte_val & 0x7F) << shift
                        if not (byte_val & 0x80):
                            break
                        shift += 7
                        if shift > 63:
                            break
                    
                    # 读取数据
                    if i + length <= len(pb_bytes):
                        data = pb_bytes[i:i+length]
                        i += length
                        
                        # 尝试解析嵌套的UserInfo消息
                        if field_num == 3:  # uinfo
                            user_info = self._parse_user_info(data)
                            if "name" in user_info and not result.get("uname"):
                                result["uname"] = user_info["name"]
                            if "face" in user_info:
                                result["face"] = user_info["face"]
                        else:
                            # 尝试解码为字符串
                            try:
                                string_value = data.decode('utf-8')
                                if field_num == 2:  # uname
                                    result["uname"] = string_value
                                elif field_num == 4:  # face
                                    result["face"] = string_value
                            except UnicodeDecodeError:
                                pass
                    else:
                        break
                        
                elif wire_type == 5:  # 32-bit fixed
                    i += 4
                
                else:
                    # 跳过未知的wire type
                    break
            
            # 确保必要字段存在
            if "uid" not in result:
                result["uid"] = 0
            if "uname" not in result:
                result["uname"] = ""
            if "msg_type" not in result:
                result["msg_type"] = 1
            if "timestamp" not in result:
                result["timestamp"] = 0
            
            return result
            
        except Exception as e:
            print(f"简化protobuf解析失败: {e}")
            return None
    
    def _parse_user_info(self, data: bytes) -> Dict:
        """解析嵌套的UserInfo消息"""
        try:
            result = {}
            i = 0
            
            while i < len(data):
                if i >= len(data):
                    break
                
                # 读取字段号和wire type
                field_info = data[i]
                i += 1
                
                field_num = field_info >> 3
                wire_type = field_info & 0x07
                
                if wire_type == 0:  # varint
                    # 跳过varint字段
                    while i < len(data) and (data[i] & 0x80):
                        i += 1
                    if i < len(data):
                        i += 1
                        
                elif wire_type == 2:  # length-delimited
                    # 读取长度
                    length = 0
                    shift = 0
                    while i < len(data):
                        byte_val = data[i]
                        i += 1
                        length |= (byte_val & 0x7F) << shift
                        if not (byte_val & 0x80):
                            break
                        shift += 7
                        if shift > 63:
                            break
                    
                    # 读取字符串数据
                    if i + length <= len(data):
                        string_data = data[i:i+length]
                        i += length
                        
                        try:
                            string_value = string_data.decode('utf-8')
                            if field_num == 1:  # face
                                result["face"] = string_value
                            elif field_num == 2:  # name
                                result["name"] = string_value
                        except UnicodeDecodeError:
                            pass
                    else:
                        break
                        
                elif wire_type == 5:  # 32-bit fixed
                    i += 4
                
                else:
                    break
            
            return result
            
        except Exception as e:
            print(f"解析UserInfo失败: {e}")
            return {}


# 创建全局解析器实例
parser = InteractWordV2Parser()


def parse_interact_word_v2(pb_data: str) -> Optional[Dict]:
    """
    解析INTERACT_WORD_V2消息的便捷函数
    
    Args:
        pb_data: base64编码的protobuf字符串
        
    Returns:
        解析后的数据字典
    """
    return parser.parse(pb_data)


if __name__ == "__main__":
    # 测试解析器
    test_data = {
        "cmd": "INTERACT_WORD_V2",
        "data": {
            "dmscore": 3,
            "pb": "CJTwwNEBEgpTdGFyU2VhMjQ2IgIDASgBMNWgITispaTDBkDUubHe/jJKLAiv8CkQEhoG55Sf5oCBIKS6ngYopLqeBjCkup4GOKS6ngZAAWDVoCFo9JQRYgB4gZ/v1tmc"
        }
    }
    
    print("测试INTERACT_WORD_V2解析器")
    print("=" * 50)
    
    pb_data = test_data["data"]["pb"]
    result = parse_interact_word_v2(pb_data)
    
    if result:
        print("解析成功:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("解析失败")