# Step 12: 调试与故障排查指南

> 当 OpenCode 工作不正常时，如何定位和解决问题

---

## 1. 常见问题分类

```
OpenCode 问题
│
├── 启动问题
│   ├── 安装失败
│   ├── 配置加载错误
│   └── 数据库初始化失败
│
├── 运行时问题
│   ├── LLM 调用失败
│   ├── 工具执行错误
│   ├── 权限被拒绝
│   └── 上下文溢出
│
├── 性能问题
│   ├── 响应慢
│   ├── Token 消耗过快
│   └── 内存占用高
│
└── 功能问题
    ├── 工具不可用
    ├── MCP 连接失败
    └── Agent 行为异常
```

---

## 2. 日志与调试

### 2.1 启用详细日志

```bash
# 方式 1: 使用 --print-logs 标志
opencode --print-logs

# 方式 2: 设置环境变量
DEBUG=opencode:* opencode

# 方式 3: 查看日志文件
tail -f ~/.opencode/logs/opencode.log
```

### 2.2 关键日志位置

```
~/.opencode/
├── logs/
│   ├── opencode.log           # 主日志
│   ├── error.log              # 错误日志
│   └── sessions/
│       └── sess_xxx.log       # 会话级日志
│
└── cache/
    └── debug/
        └── prompts/           # 发送给 LLM 的 Prompt
            └── sess_xxx/
                ├── system.txt
                └── messages.json
```

### 2.3 日志级别

```typescript
// packages/opencode/src/util/log.ts

export enum LogLevel {
  DEBUG = 0,   // 详细调试信息
  INFO = 1,    // 一般信息
  WARN = 2,    // 警告
  ERROR = 3,   // 错误
}

// 使用示例
const log = Log.create({ service: "session.processor" })
log.debug("Processing message", { messageID })
log.info("Session started", { sessionID })
log.warn("Context approaching limit", { tokens })
log.error("Failed to execute tool", { error })
```

---

## 3. 启动问题排查

### 3.1 安装失败

```bash
# 问题：bun install 失败

# 排查步骤：
1. 检查 bun 版本
   bun --version  # 需要 >= 1.0.0

2. 清理缓存重试
   rm -rf node_modules bun.lockb
   bun install

3. 检查网络
   curl -I https://registry.npmjs.org
```

### 3.2 配置加载错误

```bash
# 问题：启动时报配置错误

# 排查步骤：
1. 验证配置文件格式
   opencode debug config

2. 检查 YAML 语法
   # 使用在线 YAML 验证器
   # 或安装 yq 工具
   yq ~/.opencode/opencode.yml

3. 查看具体错误
   opencode --print-logs 2>&1 | grep -i "config"
```

### 3.3 数据库初始化失败

```bash
# 问题：SQLite 数据库锁定或损坏

# 解决方案：
1. 关闭所有 opencode 进程
   pkill -f opencode

2. 检查数据库文件
   ls -la ~/.opencode/sessions.db

3. 备份并重建（数据会丢失！）
   mv ~/.opencode/sessions.db ~/.opencode/sessions.db.bak
   opencode  # 会自动创建新数据库

4. 修复（如果可能）
   sqlite3 ~/.opencode/sessions.db ".recover" | sqlite3 ~/.opencode/sessions.db.fixed
```

---

## 4. 运行时问题排查

### 4.1 LLM 调用失败

#### 症状
```
Error: Failed to call LLM
Status: 429
Message: Rate limit exceeded
```

#### 排查步骤

```bash
# 1. 检查 API Key
opencode debug provider

# 2. 验证 API 连接
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY"

# 3. 检查配额
# 登录 Provider 控制台查看用量

# 4. 切换 Provider（临时）
# 在对话中输入：
/model openai/gpt-4o
```

#### 常见错误码

| 错误码 | 含义 | 解决方案 |
|--------|------|----------|
| 401 | API Key 无效 | 检查环境变量或配置文件 |
| 429 | 速率限制 | 等待或降低调用频率 |
| 500 | Provider 内部错误 | 稍后重试或切换 Provider |
| 529 | 服务过载 | 使用其他模型或等待 |

### 4.2 工具执行错误

#### Bash 命令失败

```bash
# 症状：bash 工具返回错误

# 排查：
1. 检查命令语法
   # 手动在终端执行相同命令

2. 检查工作目录
   # 确认 cwd 参数正确

3. 检查权限
   ls -la $(pwd)

4. 查看详细错误
   # 在 opencode 中查看 tool result 的 error 字段
```

#### 文件操作失败

```bash
# 症状：read/edit 失败

# 排查：
1. 检查文件是否存在
   ls -la <filepath>

2. 检查权限
   # 是否有读/写权限

3. 检查路径
   # 是相对路径还是绝对路径
   # 工作目录是否正确

4. 检查 external_directory 权限
   # 如果文件在项目外，需要权限
```

### 4.3 权限被拒绝

```
症状：Permission denied: bash
```

#### 排查

```bash
# 1. 查看当前权限配置
opencode debug permission

# 2. 检查 Agent 配置
# 查看 ~/.opencode/opencode.yml

# 3. 临时允许（不推荐长期使用）
# 在配置中添加：
permission:
  bash: allow

# 4. 检查具体拒绝原因
opencode --print-logs 2>&1 | grep -i "permission"
```

### 4.4 上下文溢出

```
症状：Context overflow error
或者：Conversation too long
```

#### 自动处理

OpenCode 会自动触发 Compaction：
```
1. 检测 isOverflow()
2. 触发 SessionCompaction.create()
3. AI 生成摘要
4. 继续对话
```

#### 手动处理

```bash
# 如果自动 compaction 失败

# 1. 开启新会话
/new

# 2. 或者手动触发 compaction
/compact

# 3. 查看当前 token 使用
/status
```

---

## 5. 性能问题排查

### 5.1 响应慢

#### 诊断

```bash
# 1. 查看耗时统计
opencode --print-logs 2>&1 | grep -E "(duration|latency|time)"

# 2. 检查具体步骤耗时
# 在日志中搜索：
# - "resolveTools" - 工具解析
# - "LLM.stream" - LLM 调用
# - "SessionCompaction" - 压缩
```

#### 优化建议

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 首次响应慢 | 工具列表太长 | 减少可用工具数量 |
| LLM 响应慢 | 模型选择 | 使用更快的模型（如 gpt-4o-mini）|
| 工具执行慢 | 命令复杂 | 简化命令或增加超时时间 |
| Compaction 慢 | 历史太长 | 主动开启新会话 |

### 5.2 Token 消耗过快

#### 监控

```bash
# 查看会话统计
/stats

# 输出示例：
# Session: sess_xxx
# Total tokens: 45,230
# Total cost: $0.23
# Messages: 15
```

#### 优化

```yaml
# ~/.opencode/opencode.yml

# 1. 使用更小的模型
agent:
  default:
    model: openai/gpt-4o-mini  # 更便宜

# 2. 限制工具数量
permission:
  websearch: deny  # 禁用昂贵工具
  codesearch: deny

# 3. 缩短 AGENTS.md
# 移除不必要的说明
```

### 5.3 内存占用高

```bash
# 检查内存使用
ps aux | grep opencode

# 常见问题：
# 1. 会话太多
# 解决：关闭旧会话 /close <session_id>

# 2. 缓存文件过大
# 解决：清理缓存
rm -rf ~/.opencode/cache/*

# 3. 内存泄漏（罕见）
# 解决：重启 opencode
```

---

## 6. 功能问题排查

### 6.1 工具不可用

```
症状：Tool not found: xxx
```

#### 排查

```bash
# 1. 检查工具列表
/tools

# 2. 检查 Agent 权限
opencode debug permission | grep xxx

# 3. 检查工具注册
opencode --print-logs 2>&1 | grep -i "registry"

# 4. 对于 MCP 工具
# 检查 MCP 服务器状态
opencode debug mcp
```

### 6.2 MCP 连接失败

```bash
# 症状：MCP tools not available

# 排查：
1. 检查 MCP 配置
   cat ~/.opencode/opencode.yml | grep -A 5 mcp

2. 测试 MCP 服务器
   # 手动运行 MCP 命令
   npx -y @modelcontextprotocol/server-filesystem .

3. 查看 MCP 日志
   opencode --print-logs 2>&1 | grep -i mcp

4. 重启 MCP 连接
   /mcp restart
```

### 6.3 Agent 行为异常

```
症状：Agent 不遵循指令，或行为不符合预期
```

#### 排查

```bash
# 1. 检查当前 Agent
/agent

# 2. 查看 Agent Prompt
opencode debug prompt

# 3. 检查 AGENTS.md 是否加载
opencode --print-logs 2>&1 | grep -i "agents.md"

# 4. 重置 Agent
/agent reset

# 5. 切换 Agent
/agent build
```

---

## 7. 调试技巧

### 7.1 查看发送给 LLM 的完整 Prompt

```bash
# 方法 1: 使用 debug 命令
opencode debug prompt --session sess_xxx

# 方法 2: 查看缓存文件
cat ~/.opencode/cache/debug/prompts/sess_xxx/system.txt
cat ~/.opencode/cache/debug/prompts/sess_xxx/messages.json

# 方法 3: 在代码中打印
# 修改 packages/opencode/src/session/llm.ts
console.log("System Prompt:", system)
console.log("Messages:", messages)
```

### 7.2 跟踪工具调用

```bash
# 查看工具调用链
opencode --print-logs 2>&1 | grep -E "(tool-call|tool-result|execute)"

# 输出示例：
# [session.processor] tool-call: bash
# [tool.bash] execute: ls -la
# [tool.bash] result: { output: "..." }
# [session.processor] tool-result: bash
```

### 7.3 分析 Token 使用

```bash
# 查看详细 token 统计
opencode --print-logs 2>&1 | grep -i "token"

# 在每步结束时查看：
# [session.processor] finish-step: {
#   tokens: { input: 5234, output: 892, cache: { read: 0, write: 0 } },
#   cost: 0.023
# }
```

### 7.4 数据库查询

```bash
# 直接查询 SQLite 数据库

# 查看会话列表
sqlite3 ~/.opencode/sessions.db "SELECT id, title, time_created FROM messages WHERE role='user' GROUP BY session_id;"

# 查看消息详情
sqlite3 ~/.opencode/sessions.db "SELECT role, data FROM messages WHERE session_id='sess_xxx' ORDER BY time_created;"

# 查看 parts
sqlite3 ~/.opencode/sessions.db "SELECT type, data FROM parts WHERE session_id='sess_xxx';"
```

---

## 8. 常见问题速查表

### Q: OpenCode 卡住了怎么办？

```bash
# 1. 检查是否正在等待权限
# 查看界面是否有权限请求提示

# 2. 发送中断信号
Ctrl+C

# 3. 如果还是卡住
pkill -f opencode
```

### Q: 如何重置会话？

```bash
# 方法 1: 软重置（保留历史）
/reset

# 方法 2: 开启新会话
/new

# 方法 3: 硬重置（删除会话）
/close <session_id>
```

### Q: 为什么工具调用很慢？

```bash
# 1. 检查网络
ping google.com

# 2. 检查超时设置
# 默认 bash 超时是 2 分钟

# 3. 简化命令
# 避免处理大量数据的命令
```

### Q: 如何导出会话记录？

```bash
# 方法 1: 使用 /export 命令
/export session.md

# 方法 2: 直接导出数据库
sqlite3 ~/.opencode/sessions.db ".dump" > backup.sql

# 方法 3: 复制会话文件
cp ~/.opencode/sessions.db ./backup.db
```

---

## 9. 报告问题

如果以上方法都无法解决问题，可以：

### 9.1 收集信息

```bash
# 1. 系统信息
opencode debug system > system_info.txt

# 2. 配置信息
opencode debug config > config_info.txt

# 3. 错误日志
opencode --print-logs 2>&1 | tail -n 100 > error_log.txt

# 4. 打包
zip debug_info.zip system_info.txt config_info.txt error_log.txt
```

### 9.2 提交 Issue

```
GitHub: https://github.com/anomalyco/opencode/issues

请包含：
1. OpenCode 版本: opencode --version
2. 操作系统: macOS/Linux/Windows
3. 问题描述
4. 复现步骤
5. 错误日志（debug_info.zip）
```

---

## 10. 总结

### 调试流程图

```
遇到问题
   │
   ▼
查看错误信息
   │
   ├── 权限问题 → 检查 permission 配置
   │
   ├── 网络问题 → 检查 API Key / 网络连接
   │
   ├── 工具错误 → 手动执行命令验证
   │
   └── 性能问题 → 查看 token 使用 / 简化任务
   │
查看日志 (--print-logs)
   │
   ▼
定位问题根源
   │
   ▼
应用解决方案
   │
   ▼
验证是否解决
```

### 关键命令速查

| 命令 | 用途 |
|------|------|
| `opencode --print-logs` | 启用详细日志 |
| `opencode debug config` | 检查配置 |
| `opencode debug permission` | 检查权限 |
| `opencode debug provider` | 检查 Provider |
| `/status` | 查看会话状态 |
| `/stats` | 查看统计信息 |
| `/tools` | 查看可用工具 |
| `/agent` | 查看当前 Agent |

---

**遇到问题不要怕，按步骤排查，大多数问题都能解决！**
