# 安全修复说明

## 已修复的问题

### 1. 硬编码API密钥泄露 ✅
**问题**: Moonshot API密钥硬编码在 `plugins/ai_reply.py` 中
**修复**: 
- 修改为从环境变量 `MOONSHOT_API_KEY` 读取
- 优先使用环境变量，其次使用配置文件
- 未设置时显示警告信息

**配置方法**:
```bash
# 方式1: 设置环境变量
export MOONSHOT_API_KEY=your_api_key_here

# 方式2: 在 .env 文件中配置
echo "MOONSHOT_API_KEY=your_api_key_here" >> .env
```

### 2. 弱加密密钥问题 ✅
**问题**: 使用硬编码的密钥和盐值加密凭证
**修复**:
- 优先从环境变量读取加密密钥
- 支持自定义密钥和盐值
- 自动基于机器特征生成密钥（MAC地址 + 系统信息）
- 增加PBKDF2迭代次数到200,000次

**配置方法**:
```bash
# 设置自定义加密密钥（可选）
export BILILIVE_ENCRYPTION_KEY=your_encryption_key
export BILILIVE_ENCRYPTION_SALT=your_salt
```

### 3. 凭证文件权限问题 ✅
**问题**: 加密的Cookie凭证文件未设置访问权限
**修复**:
- 在保存凭证后自动设置文件权限为600（仅所有者可读写）
- 支持Windows和Unix-like系统

### 4. 自动欢迎插件逻辑问题 ✅
**问题**: 机器人回复后会自动发送欢迎语，导致重复消息
**修复**:
- 移除在弹幕事件中发送欢迎语的逻辑
- 仅在用户真正进入直播间时（INTERACT_WORD事件）发送欢迎语
- 增加用户欢迎间隔检查，避免重复欢迎
- 优化欢迎语生成，确保不超过20字符

### 5. 签到插件逻辑问题 ✅
**问题**: 签到指令响应不准确，消息过于冗长
**修复**:
- 简化签到成功消息为"签到成功！"
- 优化连续签到奖励消息
- 用户当天已签到时不发送消息，避免刷屏
- 移除调试日志，减少控制台输出

### 6. CSRF防护增强 ✅
**问题**: CSRF Token验证不够严格
**修复**:
- 添加完整的HTTP安全头（Referer、Origin、Sec-Fetch-*）
- 增强参数验证
- 保持WBI签名机制

### 7. WebSocket身份验证 ✅
**问题**: WebSocket连接未验证身份
**修复**:
- 添加Token查询参数支持
- 预留身份验证接口（可选启用）
- 支持通过 `WS_TOKEN_SECRET` 配置

## 配置步骤

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
复制示例配置文件：
```bash
cp .env.example .env
```

编辑 `.env` 文件，至少配置以下内容：
```env
MOONSHOT_API_KEY=your_moonshot_api_key_here
```

### 3. 启动服务
```bash
python start.py
```

### 4. 访问Web界面
打开浏览器访问: http://127.0.0.1:8001

## 插件配置

### AI智能回复插件
- 在配置文件中填入Moonshot API Key
- 调整回复概率、间隔等参数
- 支持自定义系统提示词

### 自动欢迎插件
- 支持自定义欢迎语列表
- 可设置欢迎间隔和频率限制
- 支持忽略特定用户

### 签到抽签插件
- 可自定义签到命令和抽签命令
- 支持连续签到奖励配置
- 可调整抽签冷却时间

## 安全建议

1. **不要将API密钥提交到版本控制系统**
   - 使用 `.gitignore` 忽略 `.env` 文件
   - 使用环境变量或密钥管理服务

2. **在生产环境中使用HTTPS**
   - 配置反向代理（如Nginx）
   - 使用SSL证书

3. **定期更新依赖**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

4. **监控日志**
   - 关注异常登录尝试
   - 监控API调用频率

5. **备份重要数据**
   - 定期备份 `data/` 目录
   - 备份配置文件

## 故障排查

### AI回复不工作
- 检查是否设置了 `MOONSHOT_API_KEY`
- 验证API Key是否有效
- 查看控制台错误信息

### 无法登录
- 检查网络连接
- 清除浏览器缓存
- 删除 `data/credential.enc` 文件重新登录

### 弹幕发送失败
- 检查是否已登录
- 验证直播间ID是否正确
- 查看控制台错误信息

## 技术支持

如遇问题，请检查：
1. Python版本 >= 3.11
2. 所有依赖是否正确安装
3. 网络连接是否正常
4. 控制台错误日志