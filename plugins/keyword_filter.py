# -*- coding: utf-8 -*-
"""
关键词过滤插件
支持黑白名单、正则表达式过滤
"""

import re
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase


class KeywordFilterPlugin(PluginBase):
    """关键词过滤插件"""
    
    name = "关键词过滤"
    description = "过滤包含特定关键词的弹幕，支持黑白名单和正则表达式"
    version = "1.0.0"
    author = "BililiveRobot"
    
    config_schema = [
        {
            "key": "mode",
            "label": "过滤模式",
            "type": "select",
            "options": [
                {"label": "黑名单模式", "value": "blacklist"},
                {"label": "白名单模式", "value": "whitelist"}
            ],
            "default": "blacklist"
        },
        {
            "key": "keywords",
            "label": "关键词列表（每行一个）",
            "type": "textarea",
            "default": "广告\n刷屏\n违规"
        },
        {
            "key": "use_regex",
            "label": "启用正则表达式",
            "type": "boolean",
            "default": False
        },
        {
            "key": "case_sensitive",
            "label": "区分大小写",
            "type": "boolean",
            "default": False
        },
        {
            "key": "filter_action",
            "label": "过滤动作",
            "type": "select",
            "options": [
                {"label": "隐藏弹幕", "value": "hide"},
                {"label": "标记弹幕", "value": "mark"},
                {"label": "替换内容", "value": "replace"}
            ],
            "default": "mark"
        },
        {
            "key": "replace_text",
            "label": "替换文本",
            "type": "text",
            "default": "[已过滤]"
        }
    ]
    
    def __init__(self):
        super().__init__()
        
        # 编译正则表达式
        self.patterns = []
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译关键词为正则表达式"""
        keywords_text = self.config.get("keywords", "")
        keywords = [k.strip() for k in keywords_text.split("\n") if k.strip()]
        
        use_regex = self.config.get("use_regex", False)
        case_sensitive = self.config.get("case_sensitive", False)
        
        self.patterns = []
        
        for keyword in keywords:
            try:
                if use_regex:
                    # 直接使用正则表达式
                    flags = 0 if case_sensitive else re.IGNORECASE
                    pattern = re.compile(keyword, flags)
                    self.patterns.append(pattern)
                else:
                    # 对于普通关键词，生成多种匹配模式
                    flags = 0 if case_sensitive else re.IGNORECASE
                    
                    # 1. 精确匹配（转义特殊字符）
                    escaped = re.escape(keyword)
                    pattern = re.compile(escaped, flags)
                    self.patterns.append(pattern)
                    
                    # 2. 为每个关键词生成允许任意空格的变体
                    # 将每个字符之间插入\s*，允许零个或多个空格
                    spaced_chars = []
                    for char in keyword:
                        spaced_chars.append(re.escape(char))
                    
                    spaced_pattern = r'\s*'.join(spaced_chars)
                    pattern = re.compile(spaced_pattern, flags)
                    self.patterns.append(pattern)
                        
            except re.error as e:
                print(f"正则表达式编译失败: {keyword}, 错误: {e}")
    
    def update_config(self, new_config):
        """更新配置时重新编译正则表达式"""
        super().update_config(new_config)
        self._compile_patterns()
    
    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """处理弹幕事件"""
        content = data.get("content", "")
        mode = self.config.get("mode", "blacklist")
        filter_action = self.config.get("filter_action", "mark")
        
        # 检查是否匹配关键词
        matched = self._check_match(content)
        
        # 根据模式决定是否过滤
        should_filter = False
        if mode == "blacklist" and matched:
            should_filter = True
        elif mode == "whitelist" and not matched:
            should_filter = True
        
        if should_filter:
            # 执行过滤动作
            if filter_action == "hide":
                # 隐藏弹幕（返回 None 表示不显示）
                return None
            elif filter_action == "mark":
                # 标记弹幕
                data["filtered"] = True
                data["filter_reason"] = "关键词过滤"
            elif filter_action == "replace":
                # 替换内容
                replace_text = self.config.get("replace_text", "[已过滤]")
                data["original_content"] = content
                data["content"] = replace_text
                data["filtered"] = True
        
        return data
    
    def _check_match(self, text: str) -> bool:
        """
        检查文本是否匹配关键词
        
        Args:
            text: 要检查的文本
            
        Returns:
            bool: 是否匹配
        """
        for pattern in self.patterns:
            if pattern.search(text):
                return True
        return False
