# Step 10: 工作流总结与扩展机制

## 概览

经过前 9 个步骤，我们已经完整了解了 OpenCode 的主工作流。本步骤作为总结篇，将梳理整体架构，并介绍系统的扩展机制。

---

## 1. 完整工作流回顾

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           OpenCode 完整工作流                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   用户输入                                                                        │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 1: 用户输入处理 (message-v2.ts)                                     │  │
│   │ - 解析 text/file/agent/mcp_resource parts                                │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 2: Agent 选择 (agent.ts)                                            │  │
│   │ - 匹配 Agent 配置（name/description/model）                              │  │
│   │ - 应用 3 层权限合并                                                      │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 3: 加载 Agent 配置                                                  │  │
│   │ - 合并 defaults/agent/session 三层配置                                   │  │
│   │ - 绑定到消息                                                             │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 4: 会话状态检查 (compaction.ts)                                     │  │
│   │ - 检查 isOverflow（context - output - buffer）                           │  │
│   │ - 触发自动 Compaction                                                    │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 5: System Prompt 组装 (system.ts, instruction.ts)                   │  │
│   │ - environment: 系统上下文                                                │  │
│   │ - provider: 模型特定指令                                                 │  │
│   │ - skills: 可用 Skill 列表                                                │  │
│   │ - instructions: AGENTS.md 项目规则                                       │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 6: Tool List 组装 (registry.ts, resolveTools)                       │  │
│   │ - ToolRegistry.all(): 获取所有工具                                       │  │
│   │ - 权限过滤 + MCP 合并                                                    │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 7: 第一次 LLM 调用 (processor.ts)                                   │  │
│   │ - streamText(): 流式调用                                                 │  │
│   │ - 事件处理（text-delta/tool-call/reasoning/finish-step）                 │  │
│   │ - Doom Loop 检测                                                         │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 8: Tool 执行 (tool.ts)                                              │  │
│   │ - 创建 Tool Part → 执行 → 更新状态                                       │  │
│   │ - 权限检查（external_directory + bash）                                  │  │
│   │ - 超时/取消处理                                                          │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 9: Tool Results 处理与第二次 LLM 调用 (message-v2.ts)                │  │
│   │ - MessageV2.toModelMessages(): 格式转换                                  │  │
│   │ - 第二次 LLM 调用                                                        │  │
│   │ - 循环控制（结束或继续）                                                 │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   返回结果给用户 / 继续循环                                                        │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心架构图

### 2.1 数据流架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   用户输入   │────▶│  MessageV2  │────▶│   Session   │────▶│    Agent    │
│  (CLI/GUI)  │     │   Format    │     │   Storage   │     │  Selection  │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                                                                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   结果输出   │◀────│  Stream     │◀────│   LLM API   │◀────│   Prompt    │
│  (UI 展示)   │     │  Response   │     │ (Vercel AI) │     │   Assembly  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                    │
                              ┌─────────────┐     ┌─────────────┐    │
                              │   Tool      │◀────│   Tool      │◀───┘
                              │  Execution  │     │   Registry  │
                              └─────────────┘     └─────────────┘
```

### 2.2 模块依赖关系

```
session/
├── prompt.ts          # 主入口，协调整个工作流
├── processor.ts       # LLM 流式处理
├── message-v2.ts      # 消息格式定义与转换
├── compaction.ts      # 上下文压缩
├── system.ts          # System Prompt 组装
└── instruction.ts     # AGENTS.md 指令加载

tool/
├── registry.ts        # 工具注册与发现
├── bash.ts            # Bash 命令执行
├── read.ts            # 文件读取
├── edit.ts            # 文件编辑
├── task.ts            # 子任务（Subagent）
└── skill.ts           # Skill 工具

agent/
├── agent.ts           # Agent 定义与加载
├── defaults.ts        # 默认配置
└── prompt/            # Agent 专用 Prompt

permission/
└── next.ts            # 权限系统

provider/
├── provider.ts        # Provider 抽象
├── transform.ts       # 模型适配
└── error.ts           # 错误处理
```

---

## 3. 扩展机制

### 3.1 Plugin 系统

OpenCode 支持插件扩展，可以在关键节点注入自定义逻辑：

```typescript
// 插件钩子点（部分）

// 1. 工具执行前后
Plugin.trigger("tool.execute.before", { tool, sessionID, callID }, { args })
Plugin.trigger("tool.execute.after", { tool, sessionID, callID, args }, output)

// 2. 消息转换
Plugin.trigger("experimental.chat.messages.transform", {}, { messages })
```

**用途**：
- 自定义工具执行前后的日志记录
- 消息内容过滤或转换
- 集成外部监控系统

### 3.2 MCP (Model Context Protocol)

MCP 允许外部服务为 OpenCode 提供工具：

```yaml
# ~/.opencode/opencode.yml

mcp:
  servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    github:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
```

**工作流程**：
```
OpenCode ──启动──▶ MCP Server (stdio/SSE)
   │                      │
   │◀────工具列表────────│
   │                      │
   │────工具调用────────▶│
   │◀────执行结果────────│
```

### 3.3 Skill 系统

Skill 提供特定领域的知识和工具：

```typescript
// Skill 结构
.skills/
├── analyze-page-flow/
│   ├── SKILL.md          # Skill 描述和使用说明
│   └── ...               # 相关资源
└── content-summarizer/
    ├── SKILL.md
    └── ...
```

**加载方式**：
```
System Prompt 中列出可用 Skills
      ↓
AI 判断需要使用某个 Skill
      ↓
调用 skill({ name: "analyze-page-flow" })
      ↓
加载 Skill 的 SKILL.md 内容到上下文
```

### 3.4 自定义工具

可以通过配置文件添加自定义工具：

```yaml
# ~/.opencode/opencode.yml

tools:
  my-custom-tool:
    description: "描述工具用途"
    parameters:
      input:
        type: string
        description: "输入参数"
    command: |
      # 执行命令
      echo "Processing: {{input}}"
```

---

## 4. 状态管理

### 4.1 会话状态

```
Session (会话)
├── id: string                    # 会话唯一 ID
├── parentID?: string             # 父会话 ID（子任务用）
├── title: string                 # 会话标题
├── permission: Permission[]      # 会话级权限
└── Messages[]                    # 消息列表
    ├── UserMessage
    │   ├── parts: TextPart[]
    │   ├── parts: FilePart[]
    │   └── parts: SubtaskPart[]
    └── AssistantMessage
        ├── parts: TextPart[]
        ├── parts: ToolPart[]
        └── parts: ReasoningPart[]
```

### 4.2 数据持久化

```typescript
// SQLite 数据库结构

messages table:
  - id, session_id, role, agent, model, time_created, data

parts table:
  - id, message_id, session_id, type, data

// 文件存储
~/.opencode/
├── sessions.db          # SQLite 数据库
├── cache/               # 缓存文件
└── config.yml           # 用户配置
```

---

## 5. 关键设计决策

### 5.1 为什么使用 MessageV2 格式？

| 传统格式 | MessageV2 |
|---------|-----------|
| 简单字符串 | 富文本 Parts |
| 难以扩展 | 支持 text/file/tool/reasoning 等多种类型 |
| 无元数据 | 每个 Part 可携带完整元数据 |

### 5.2 为什么选择流式处理？

- **用户体验**：实时看到 AI 打字效果
- **早期干预**：发现问题可立即取消
- **资源效率**：不需要等待完整响应

### 5.3 为什么分离 System Prompt 和 User Message？

```
System Prompt: 告诉 AI "你是谁，你能做什么"
User Message:  告诉 AI "用户想要什么"

分离的好处：
1. 清晰的职责边界
2. 便于缓存（System Prompt 变化少）
3. 支持多轮对话历史
```

### 5.4 为什么需要 Doom Loop 检测？

```
场景：AI 陷入重复调用同一个工具的循环

没有检测：
  AI: bash("ls src/") → 失败
  AI: bash("ls src/") → 失败  
  AI: bash("ls src/") → 失败
  ...无限循环，浪费 Token

有检测：
  AI: bash("ls src/") → 失败
  AI: bash("ls src/") → 失败
  AI: bash("ls src/") → 检测到 Doom Loop
  系统：询问用户是否继续
```

---

## 6. 性能优化策略

### 6.1 上下文压缩

| 机制 | 触发条件 | 效果 |
|------|----------|------|
| **Prune** | 每次 step 后 | 删除旧 tool outputs |
| **Compaction** | 溢出时 | AI 生成摘要 |
| **Tool Result 清理** | Compaction 时 | 替换为占位符 |

### 6.2 Token 使用估算

```
单次调用组成：
├── System Prompt: ~2K-5K tokens
├── Tools Description: ~3K-8K tokens（取决于工具数量）
├── Messages History: ~可变
│   └── 每轮对话: ~500-2000 tokens
└── Output: ~500-4000 tokens

200K 上下文可用约 180K：
- 固定开销: ~10K
- 可用对话历史: ~170K
- 约支持 50-100 轮对话
```

### 6.3 缓存策略

```typescript
// Prompt Caching (Claude)
const system = [
  ...(await SystemPrompt.environment(model)),  // 可缓存
  ...(skills ? [skills] : []),                  // 相对固定，可缓存
  ...(await InstructionPrompt.system()),        // 项目级，可缓存
]
```

---

## 7. 错误处理机制

### 7.1 层级化的错误处理

```
Level 1: Tool 级别
  - 工具执行失败 → 更新 Part 状态为 error
  - 返回错误信息给 LLM

Level 2: Step 级别
  - LLM 调用失败 → 重试或报错
  - 上下文溢出 → 触发 Compaction

Level 3: Session 级别
  - 权限被拒绝 → 询问用户
  - Doom Loop 检测 → 询问用户

Level 4: 全局级别
  - Provider API 错误 → 切换 Provider 或报错
  - 未知错误 → 记录日志并退出
```

### 7.2 优雅降级

```
场景：MCP 工具调用失败
├── 尝试重连 MCP Server
├── 如果失败，从工具列表中移除该 MCP 的工具
└── 继续对话，不影响其他功能
```

---

## 8. 与其他系统的对比

| 特性 | OpenCode | Claude Code | GitHub Copilot Chat |
|------|----------|-------------|---------------------|
| **Agent 系统** | ✅ 多 Agent | ✅ 内置多模式 | ❌ 单一模式 |
| **本地运行** | ✅ 完全本地 | ✅ 本地 CLI | ❌ 云端 |
| **MCP 支持** | ✅ 完整支持 | ❌ 不支持 | ❌ 不支持 |
| **自定义工具** | ✅ 支持 | ❌ 不支持 | ❌ 不支持 |
| **Plan 模式** | ✅ 内置 | ✅ 内置 | ❌ 不支持 |
| **开源** | ✅ 开源 | ❌ 闭源 | ❌ 闭源 |

---

## 9. 最佳实践

### 9.1 配置建议

```yaml
# ~/.opencode/opencode.yml

# 1. 为不同项目配置不同的 Agent
agent:
  frontend-dev:
    name: "frontend-dev"
    description: "Specialized in React/TypeScript frontend development"
    mode: "primary"
    permission:
      "*": "allow"
      "bash": "ask"  # 谨慎执行命令

# 2. 配置常用 MCP
mcp:
  servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "."]

# 3. 项目级指令
instructions:
  - "AGENTS.md"
  - "docs/project-rules.md"
```

### 9.2 AGENTS.md 编写建议

```markdown
# AGENTS.md

## 技术栈
- 框架: Next.js 14 + React 18
- 语言: TypeScript
- 样式: Tailwind CSS
- 测试: Vitest

## 代码规范
- 使用函数式组件
- Props 使用 interface 定义
- 测试文件与源文件同级

## 常用命令
- 运行测试: `bun test`
- 类型检查: `bun typecheck`
- 构建: `bun run build`

## 注意事项
- 不要修改 .env 文件
- 提交前必须跑通测试
```

---

## 10. 未来展望

### 可能的改进方向

1. **更智能的上下文管理**
   - 基于语义的 compaction（不只是截断）
   - 自动识别关键信息并保留

2. **多模态支持**
   - 图像理解（已部分支持）
   - 视频分析
   - 音频处理

3. **协作功能**
   - 多人同时编辑
   - 会话共享和评论

4. **更强大的 Agent 系统**
   - Agent 之间的协作
   - 动态 Agent 创建

---

## 11. 文档系列总结

### 已完成的文档

| 文档 | 内容 |
|------|------|
| Step 1 | 用户输入处理（MessageV2 格式） |
| Step 2 | Agent 选择与权限系统 |
| Step 3 | Agent 配置加载与合并 |
| Step 4 | 会话状态检查与 Compaction |
| Step 5 | System Prompt 组装 |
| Step 6 | Tool List 组装与权限过滤 |
| Step 7 | LLM 流式调用与事件处理 |
| Step 8 | Tool 执行（以 Bash 为例） |
| Step 9 | Tool Results 处理与循环控制 |
| Step 10 | 工作流总结与扩展机制 |

### 待深入研究（todo-thinking-items.md）

1. **BatchTool 实现** - 并行工具调用的内部机制
2. **大量 Tools/Skills/MCPs 的提示词规划** - 上下文空间优化
3. **主循环机制** - 架构设计与可能的优化

---

## 12. 结语

OpenCode 的设计理念：

> **简单、透明、可扩展**

- **简单**：清晰的工作流，每个步骤职责明确
- **透明**：用户可以看到 AI 的每一步操作
- **可扩展**：Plugin、MCP、Skill 三层扩展机制

通过这 10 个步骤的深入分析，你应该已经理解了 OpenCode 的核心工作原理。希望这些文档对你使用或贡献 OpenCode 有所帮助！

---

**Happy Coding! 🚀**
