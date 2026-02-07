# B站直播弹幕监控改进方案

## 问题分析

当前系统无法正确获取进入直播间的用户名，主要原因是：

1. **WATCHED_CHANGE 事件不是用户进入事件**
   - 它只是观看人数更新：`{'num': 438, 'text_small': '438', 'text_large': '438人看过'}`
   - 不包含任何用户信息

2. **INTERACT_WORD 事件可能不包含完整的用户信息**
   - 受B站隐私政策影响，未登录用户无法查看他人昵称
   - 该事件可能不会为每个普通用户触发

## 基于 blivedm 库的改进方案

### 1. 多渠道检测用户进入

参考 blivedm 库的实现，通过多种事件检测用户进入：

```python
# 通过弹幕首次出现检测用户
def _handle_danmaku(self, data: Dict):
    user_info = data.get("user", {})
    user_name = user_info.get("uname", "")
    user_uid = user_info.get("uid", 0)
    
    if user_uid not in self.user_first_seen:
        self._trigger_user_enter(user_name, user_uid, "弹幕")

# 通过送礼检测用户
def _handle_gift(self, data: Dict):
    # 类似逻辑，记录首次送礼的用户

# 通过SC检测用户
def _handle_superchat(self, data: Dict):
    # 类似逻辑，记录首次发送SC的用户

# 通过上舰检测用户
def _handle_guard(self, data: Dict):
    # 类似逻辑，记录首次上舰的用户
```

### 2. 使用 InteractWordV2Message

blivedm 库使用了 `InteractWordV2Message` 来处理用户进入：

```python
def _on_interact_word_v2(self, client, message):
    if message.msg_type == 1:
        print(f'{message.username} 进入房间')
```

### 3. 使用 UserToastV2Message 处理舰长进入

```python
def _on_user_toast_v2(self, client, message):
    if message.source != 2:
        print(f'{message.username} 上舰')
```

### 4. 需要登录用户的 Cookie

为了获取完整的用户信息，必须提供登录用户的 cookie：

```python
# SESSDATA 是必需的
SESSDATA = '你的登录cookie中的SESSDATA值'
cookies = http.cookies.SimpleCookie()
cookies['SESSDATA'] = SESSDATA
cookies['SESSDATA']['domain'] = 'bilibili.com'
```

## 具体改进建议

### 1. 立即实施的改进

1. **添加多渠道用户检测**
   - 通过弹幕、礼物、SC、上舰等事件记录用户首次出现
   - 避免重复触发进入事件

2. **增强配置选项**
   - 添加"通过弹幕检测新用户"选项
   - 添加"通过礼物检测新用户"选项
   - 添加"通过SC检测新用户"选项

3. **改进用户进入逻辑**
   - 不再依赖 INTERACT_WORD 事件
   - 使用首次出现作为进入判断标准

### 2. 长期优化方案

1. **实现完整的 blivedm 兼容**
   - 直接使用 blivedm 库作为底层客户端
   - 保持现有插件接口不变

2. **添加用户行为分析**
   - 记录用户活跃度
   - 智能判断真正的"进入"行为

3. **优化欢迎策略**
   - 只对真正的新用户发送欢迎语
   - 根据用户来源（弹幕、礼物等）发送不同的欢迎语

## 配置示例

```json
{
  "auto_welcome": {
    "enable_welcome": true,
    "detect_from_danmaku": true,
    "detect_from_gift": true,
    "detect_from_sc": true,
    "detect_from_guard": true,
    "welcome_messages": {
      "danmaku": "欢迎 {user} 第一次发言！",
      "gift": "感谢 {user} 的礼物，欢迎来到直播间！",
      "sc": "感谢 {user} 的SC，欢迎来到直播间！",
      "guard": "感谢 {user} 上舰，欢迎来到直播间！"
    }
  }
}
```

## 实施步骤

1. **第一阶段**：修改现有代码，添加多渠道检测
2. **第二阶段**：测试并优化检测逻辑
3. **第三阶段**：添加配置选项，让用户自定义
4. **第四阶段**：考虑集成 blivedm 库

## 注意事项

1. **隐私政策**：必须使用登录用户的 cookie 才能获取完整信息
2. **性能考虑**：需要合理控制检测频率和缓存大小
3. **用户体验**：避免对同一用户重复发送欢迎语

## 相关资源

- [blivedm GitHub](https://github.com/xfgryujk/blivedm)
- [B站直播协议文档](https://github.com/xfgryujk/blivedm/blob/dev/protocol.md)
- [B站开放平台](https://open-live.bilibili.com/)