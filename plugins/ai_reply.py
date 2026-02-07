# -*- coding: utf-8 -*-
"""
弹幕AI回复插件
使用 Moonshot API 智能回复弹幕
"""

import time
import random
import asyncio
from typing import Optional, Dict, List
import sys
import os
import json
import aiohttp

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugin_system import PluginBase
from core.danmaku_sender import get_danmaku_sender
from core.room_info import get_room_info


class AIReplyPlugin(PluginBase):
    """弹幕AI回复插件"""

    name = "AI智能回复"
    description = "使用 Moonshot API 智能回复弹幕"
    version = "1.0.0"
    author = "BililiveRobot"

    config_schema = [
        {
            "key": "api_key",
            "label": "Moonshot API Key",
            "type": "string",
            "default": "",
            "description": "请从环境变量 MOONSHOT_API_KEY 读取，或在此处手动填写"
        },
        {
            "key": "model",
            "label": "模型名称",
            "type": "select",
            "options": [
                {"label": "moonshot-v1-8k", "value": "moonshot-v1-8k"},
                {"label": "moonshot-v1-32k", "value": "moonshot-v1-32k"},
                {"label": "moonshot-v1-128k", "value": "moonshot-v1-128k"}
            ],
            "default": "moonshot-v1-8k"
        },
        {
            "key": "reply_probability",
            "label": "回复概率（0-1）",
            "type": "number",
            "default": 0.1,
            "min": 0,
            "max": 1,
            "step": 0.05
        },
        {
            "key": "min_reply_interval",
            "label": "最小回复间隔（秒）",
            "type": "number",
            "default": 10,
            "min": 5,
            "max": 60
        },
        {
            "key": "max_reply_length",
            "label": "最大回复长度",
            "type": "number",
            "default": 40,
            "min": 10,
            "max": 40
        },
        {
            "key": "enable_keyword_trigger",
            "label": "启用关键词触发",
            "type": "boolean",
            "default": True
        },
        {
            "key": "trigger_keywords",
            "label": "触发关键词（逗号分隔）",
            "type": "string",
            "default": "机器人,ai,智能,助手"
        },
        {
            "key": "trigger_keyword",
            "label": "触发关键词",
            "type": "string",
            "default": "小艺",
            "description": "弹幕以此关键词开头时会触发AI回复"
        },
        {"key": "system_prompt", "label": "系统提示词", "type": "textarea", "default": "你是一个活泼可爱的B站直播助手，用简短、有趣、友好的方式回复弹幕，字数控制在30字以内。"},
        {
            "key": "temperature",
            "label": "回复创造性（0-1）",
            "type": "number",
            "default": 0.7,
            "min": 0,
            "max": 1,
            "step": 0.1
        },
        {
            "key": "enable_local_qa",
            "label": "启用本地问答库",
            "type": "boolean",
            "default": True
        },
        {
            "key": "local_qa_data",
            "label": "本地问答数据",
            "type": "textarea",
            "default": "你是谁 | 嘿嘿，我是绒绒的虚拟助手小艺～ ✨ 负责弹幕互动\n小艺是谁 | 我就是小艺呀～ ✨\n你好 | 你好呀～ ✨\n在吗 | 在的呢～ ✨\n叫什么 | 我叫小艺～ ✨\n多大 | 我是AI，没有年龄哦～\n可爱 | 谢谢夸奖～ ✨\n喜欢 | 谢谢喜欢～ ✨\n帮忙 | 当然可以，需要帮什么忙呢？✨\n谢谢 | 不客气～ ✨\n再见 | 拜拜～ ✨\n晚安 | 晚安～ ✨ 好梦！",
            "description": "格式：问题 | 回答（每行一个问答对）"
        }
    ]

    def __init__(self):
        super().__init__()

        # 回复历史
        self.reply_history = []
        self.last_reply_time = 0

        # 最近弹幕缓存（用于上下文）
        self.recent_danmaku = []

        # 简单的回复缓存（避免重复调用）
        self.reply_cache = {}
        self.cache_max_size = 100

        # WebSocket管理器引用（将在初始化时设置）
        self.ws_manager = None

        # 房间号（需要从外部设置）
        self._room_id = 0

        # API配置 - 优先从环境变量读取API密钥
        import os
        api_key = os.environ.get('MOONSHOT_API_KEY', '') or self.config.get('api_key', '')
        self.api_base = "https://api.moonshot.cn/v1"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        if not api_key:
            print("[警告] 未设置 Moonshot API Key，AI回复功能将无法使用")
            print("请设置环境变量 MOONSHOT_API_KEY 或在配置中填写 API Key")

        # 初始化本地问答库
        self.local_qa = {}

    def load_config(self):
        """加载插件配置"""
        super().load_config()
        # 在配置加载后初始化问答库
        self._load_local_qa()

    def set_websocket_manager(self, ws_manager):
        """设置WebSocket管理器引用"""
        self.ws_manager = ws_manager

    async def on_danmaku(self, data: dict) -> Optional[dict]:
        """处理弹幕事件"""
        current_time = time.time()

        # 获取弹幕内容
        content = data.get("content", "").strip()
        user_name = data.get("user", {}).get("uname", "")
        user_id = data.get("user", {}).get("uid", 0)

        # 检查是否为机器人自己的弹幕（必须在最前面检查）
        from core.user_manager import user_manager
        if user_manager.is_current_user(user_id, user_name):
            return data  # 直接返回，不做任何处理

        # 过滤空弹幕和太短的弹幕
        if not content:
            return data

        # 过滤系统指令（签到、抽签等）- 不拦截，让签到插件处理
        system_commands = ["签到", "抽签"]
        if content in system_commands:
            return data  # 直接返回，让其他插件处理

        # 过滤只包含标点符号的弹幕
        import re
        if re.match(r'^[^\w\u4e00-\u9fff]+$', content):
            return data

        # 检查回复间隔
        time_since_last = current_time - self.last_reply_time
        min_interval = self.config.get("min_reply_interval", 10)
        if time_since_last < min_interval:
            return data

        # 检查是否需要回复
        should_reply = await self._should_reply(content, user_name)

        if should_reply:
            # 生成回复
            reply = await self._generate_reply(content, user_name)

            if reply:
                # 发送回复
                await self._send_reply(reply, content, user_name)

                # 记录回复历史
                self.reply_history.append({
                    "danmaku": content,
                    "user": user_name,
                    "reply": reply,
                    "time": current_time
                })

                # 更新最后回复时间
                self.last_reply_time = current_time

                # 保留最近100条记录
                if len(self.reply_history) > 100:
                    self.reply_history = self.reply_history[-100:]

        # 更新最近弹幕缓存
        self.recent_danmaku.append({
            "content": content,
            "user": user_name,
            "time": current_time
        })

        # 保留最近20条弹幕
        if len(self.recent_danmaku) > 20:
            self.recent_danmaku = self.recent_danmaku[-20:]

        return data

    async def _should_reply(self, content: str, user_name: str) -> bool:
        """判断是否应该回复"""
        # 关键词触发（优先级最高）
        if self.config.get("enable_keyword_trigger", True):
            trigger_keyword = self.config.get("trigger_keyword", "小艺")
            if trigger_keyword and content.startswith(trigger_keyword):
                return True

        # @机器人（如果弹幕包含@）
        if "@" in content and any(name in content for name in ["机器人", "助手", "AI", "小艺"]):
            return True

        # 随机概率（仅在非关键词触发时使用）
        rand_val = random.random()
        reply_prob = self.config.get("reply_probability", 0.1)
        if rand_val > reply_prob:
            return False

        # 关键词触发
        if self.config.get("enable_keyword_trigger", True):
            trigger_keyword = self.config.get("trigger_keyword", "小艺")
            if trigger_keyword and content.startswith(trigger_keyword):
                return True

        return False

    def set_room_id(self, room_id: int):
        """设置房间号"""
        self._room_id = room_id
    
    def _load_local_qa(self):
        """加载本地问答库"""
        try:
            qa_data = self.config.get("local_qa_data", "")
            
            # 尝试解析为JSON（兼容旧格式）
            try:
                self.local_qa = json.loads(qa_data)
            except:
                # 如果不是JSON，尝试解析为简单的问答对格式
                self.local_qa = {}
                lines = qa_data.strip().split('\n')
                for line in lines:
                    if '|' in line:
                        parts = line.split('|', 1)
                        if len(parts) == 2:
                            question = parts[0].strip()
                            answer = parts[1].strip()
                            if question and answer:
                                self.local_qa[question] = [answer]
            
            print(f"[AI回复] 已加载 {len(self.local_qa)} 条本地问答")
        except Exception as e:
            print(f"[AI回复] 加载本地问答库失败: {e}")
            self.local_qa = {}

    def _match_local_qa(self, question: str) -> Optional[str]:
        """匹配本地问答库"""
        if not self.config.get("enable_local_qa", True):
            return None

        question = question.strip()

        # 精确匹配
        if question in self.local_qa:
            answers = self.local_qa[question]
            return random.choice(answers) if answers else None

        # 模糊匹配（包含关系）
        for key, answers in self.local_qa.items():
            if key in question or question in key:
                return random.choice(answers) if answers else None

        return None

    def update_config(self, new_config: Dict):
        """更新配置时重新加载问答库"""
        super().update_config(new_config)
        self._load_local_qa()

    async def _generate_reply(self, danmaku: str, user_name: str) -> Optional[str]:
        """生成AI回复"""
        try:
            # 直播间信息查询（优先级最高）
            if self.config.get("enable_room_info_query", True):
                try:
                    # 获取房间号（从环境变量或全局配置）
                    room_id = getattr(self, '_room_id', None) or 0
                    if room_id > 0:
                        room_info = get_room_info(room_id)
                        room_answer = await room_info.handle_room_query(danmaku)
                        if room_answer:
                            print(f"[AI回复] 使用直播间信息回答")
                            return room_answer
                except Exception as e:
                    print(f"[AI回复] 直播间信息查询失败: {e}")

            # 本地问答库匹配
            local_answer = self._match_local_qa(danmaku)
            if local_answer:
                print(f"[AI回复] 使用本地问答库回答")
                return local_answer

            # 检查API密钥是否配置
            if not self.headers.get("Authorization") or self.headers["Authorization"] == "Bearer ":
                print(f"[AI回复] 未配置API密钥，无法生成AI回复")
                return None

            # 检查缓存
            cache_key = f"{user_name}:{danmaku}"
            if cache_key in self.reply_cache:
                return self.reply_cache[cache_key]

            # 获取用户记忆
            user_memory = self._get_user_memory(user_name)

            # 构建用户消息
            user_message = f"{user_name}: {danmaku}"

            # 构建对话 - 简化上下文以提高速度
            system_prompt = self.config.get("system_prompt",
                "你是一个活泼可爱的B站直播助手，用简短、有趣、友好的方式回复弹幕。"
                "回复控制在30字以内。")
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                }
            ]

            # 只添加最近3条相关弹幕作为上下文
            context_messages = []
            for msg in self.recent_danmaku[-3:]:
                if msg["user"] != user_name and len(msg["content"]) < 20:  # 只添加短消息
                    context_messages.append(f"{msg['user']}: {msg['content']}")

            if context_messages:
                messages.append({
                    "role": "user",
                    "content": "\n".join(context_messages)
                })

            # 添加当前弹幕
            messages.append({
                "role": "user",
                "content": user_message
            })

            # 调用API - 优化性能并添加重试机制
            max_retries = 3
            retryable_status_codes = [429, 500, 502, 503, 504]

            async with asyncio.timeout(10):  # 增加超时时间到10秒
                # 使用连接池优化
                connector = aiohttp.TCPConnector(
                    limit=100,  # 总连接池大小
                    limit_per_host=30,  # 每个主机的连接数
                    ttl_dns_cache=300,  # DNS缓存5分钟
                    use_dns_cache=True,
                )

                async with aiohttp.ClientSession(connector=connector) as session:
                    # 优化请求参数
                    json_data = {
                        "model": self.config.get("model", "moonshot-v1-8k"),
                        "messages": messages,
                        "temperature": self.config.get("temperature", 0.7),
                        "max_tokens": 50,  # 增加token数以支持更长的回复
                        "stream": False,
                        "stop": ["\n", "。", "！", "？"]  # 设置停止符，避免生成过长句子（最多5个）
                    }

                    # 重试循环
                    for attempt in range(max_retries):
                        async with session.post(
                            f"{self.api_base}/chat/completions",
                            headers=self.headers,
                            json=json_data
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                reply = result["choices"][0]["message"]["content"].strip()

                                # 检查回复长度
                                max_length = self.config.get("max_reply_length", 40)
                                if len(reply) > max_length:
                                    # 截断到最大长度，不加省略号
                                    reply = reply[:max_length]

                                # 避免重复回复
                                if self._is_duplicate_reply(reply):
                                    return None

                                # 清理回复内容
                                reply = self._clean_reply(reply)

                                # 添加到缓存
                                self.reply_cache[cache_key] = reply

                                # 限制缓存大小
                                if len(self.reply_cache) > self.cache_max_size:
                                    # 删除最旧的缓存项
                                    oldest_key = next(iter(self.reply_cache))
                                    del self.reply_cache[oldest_key]

                                return reply
                            elif response.status in retryable_status_codes:
                                # 可重试的错误
                                if attempt < max_retries - 1:
                                    wait_time = 2 ** attempt  # 指数退避: 1, 2, 4秒
                                    print(f"AI回复API错误: {response.status}, {wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                                    await asyncio.sleep(wait_time)
                                    continue
                                else:
                                    print(f"AI回复API错误: {response.status}, 已达到最大重试次数")
                                    return None
                            else:
                                # 不可重试的错误
                                print(f"AI回复API错误: {response.status}")
                                try:
                                    error_detail = await response.text()
                                    print(f"API错误详情: {error_detail}")
                                except:
                                    pass
                                return None

        except asyncio.TimeoutError:
            print("AI回复超时")
            return None
        except Exception as e:
            print(f"AI回复错误: {e}")
            return None

    def _clean_reply(self, reply: str) -> str:
        """清理回复内容，移除可能导致问题的字符"""
        import re
        
        # 移除控制字符（除了换行和制表符）
        reply = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', reply)
        
        # 移除可能的HTML标签
        reply = re.sub(r'<[^>]+>', '', reply)
        
        # 移除过多的特殊字符
        reply = re.sub(r'[!()*]{3,}', '', reply)
        
        # 确保回复不为空
        if not reply.strip():
            return "好的～ ✨"
        
        return reply.strip()
    
    def _is_duplicate_reply(self, reply: str) -> bool:
        """检查回复是否重复"""
        # 检查最近5条回复
        recent_replies = self.reply_history[-5:]
        for history in recent_replies:
            if history["reply"] == reply:
                return True
        return False

    async def _send_reply(self, reply: str, original_danmaku: str = "", user_name: str = ""):
        """发送回复"""
        sender = get_danmaku_sender()
        if sender:
            result = await sender.send(reply)
            if result.get("success"):
                # 通过WebSocket向前端发送AI回复消息
                await self._notify_ai_reply(original_danmaku, user_name, reply)
            else:
                print(f"AI回复发送失败: {result.get('message')}")

    async def _notify_ai_reply(self, original_danmaku: str, user_name: str, ai_reply: str):
        """通过WebSocket向前端发送AI回复消息"""
        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "ai_reply",
                    "data": {
                        "original_danmaku": original_danmaku,
                        "user_name": user_name,
                        "ai_reply": ai_reply,
                        "timestamp": time.time()
                    }
                })
            except Exception as e:
                print(f"AI回复WebSocket推送失败: {e}")

    def get_reply_stats(self) -> Dict:
        """获取回复统计"""
        current_time = time.time()

        # 统计最近1小时的回复
        recent_replies = [
            r for r in self.reply_history
            if current_time - r["time"] < 3600
        ]

        # 统计回复的用户
        replied_users = set(r["user"] for r in recent_replies)

        return {
            "total_replies": len(self.reply_history),
            "recent_replies": len(recent_replies),
            "replied_users": len(replied_users),
            "last_reply_time": self.last_reply_time,
            "recent_reply_history": recent_replies[-10:]  # 最近10条
        }

    def _get_user_memory(self, user_name: str) -> Dict:
        """获取用户记忆"""
        # 尝试从用户分析插件获取用户记忆
        try:
            # 获取用户分析插件实例
            from core.plugin_system import PluginManager
            plugin_manager = PluginManager()
            user_analytics_plugin = plugin_manager.get_plugin("用户分析")

            if user_analytics_plugin:
                return user_analytics_plugin.get_user_memory(user_name)
        except:
            pass

        # 如果无法获取，返回空记忆
        return {
            "messages": [],
            "interests": {},
            "common_topics": []
        }

    def _get_enhanced_system_prompt(self, user_name: str, user_memory: Dict) -> str:
        """获取增强的系统提示词"""
        base_prompt = self.config.get("system_prompt", "你是一个活泼可爱的B站直播助手，用简短、有趣、友好的方式回复弹幕，字数控制在15字以内。")

        # 添加用户记忆信息
        memory_info = []

        # 添加兴趣信息
        if user_memory.get("interests"):
            interests = list(user_memory["interests"].keys())[:3]  # 最多3个兴趣
            if interests:
                memory_info.append(f"用户兴趣: {', '.join(interests)}")

        # 添加常见话题
        if user_memory.get("common_topics"):
            topics = [topic["word"] for topic in user_memory["common_topics"][:5]]  # 最多5个话题
            if topics:
                memory_info.append(f"用户常聊话题: {', '.join(topics)}")

        # 添加情感倾向
        if user_memory.get("emotion_trend"):
            emotions = user_memory["emotion_trend"][-10:]  # 最近10条情感
            if emotions:
                avg_emotion = sum(emotions) / len(emotions)
                if avg_emotion > 0.2:
                    memory_info.append("用户最近情绪偏向积极")
                elif avg_emotion < -0.2:
                    memory_info.append("用户最近情绪偏向消极")

        # 构建增强的提示词
        if memory_info:
            enhanced_prompt = base_prompt + f"\n\n用户记忆信息:\n" + "\n".join(memory_info)
            enhanced_prompt += f"\n\n请根据用户的兴趣和习惯，给出更个性化的回复。记住用户的名字是{user_name}。"
            return enhanced_prompt

        return base_prompt

    def reset_history(self):
        """重置回复历史"""
        self.reply_history.clear()
        self.recent_danmaku.clear()
        self.last_reply_time = 0
        print("AI回复历史已重置")


# 导入 aiohttp 用于HTTP请求
try:
    import aiohttp
except ImportError:
    print("警告: 未安装 aiohttp，AI回复功能将无法使用")
    print("请运行: pip install aiohttp")
    aiohttp = None