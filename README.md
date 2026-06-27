# OpenCode 主工作流技术文档

本文档详细解析 OpenCode AI 编码助手的主工作流实现。

---

## 文档索引

### 核心工作流步骤

| 步骤 | 标题 | 内容概要 |
|------|------|----------|
| Step 1 | [用户输入处理](steps/step1-user-input-processing.md) | MessageV2 格式、消息 Parts、MCP Resource 处理 |
| Step 2 | [Agent 选择](steps/step2-agent-selection.md) | 三种 Agent 类型、@ 提及解析、3 层权限系统 |
| Step 3 | [加载 Agent 配置](steps/step3-load-agent-config.md) | 配置合并、权限绑定、noReply 模式 |
| Step 4 | [会话状态检查](steps/step4-check-session-state.md) | Compaction/Prune 配置、isOverflow 检测 |
| Step 5 | [System Prompt 组装](steps/step5-assemble-system-prompt.md) | 4 层 Prompt 结构、Skill 加载、指令系统 |
| Step 6 | [Tool List 组装](steps/step6-assemble-tool-list.md) | ToolRegistry、权限过滤、MCP 工具合并 |
| Step 7 | [第一次 LLM 调用](steps/step7-first-llm-call.md) | streamText、事件处理、Doom Loop 检测 |
| Step 8 | [Tool 执行](steps/step8-execute-tool-call.md) | Bash 执行流程、2 层权限、超时取消 |
| Step 9 | [User Content 组装和第二次 LLM 调用](steps/step-09-user-content-and-second-llm-call.md) | 消息格式转换、Tool Results 处理、循环控制 |
| Step 10 | [工作流总结与扩展机制](steps/step-10-summary-and-extensions.md) | 架构总结、Plugin/MCP/Skill 扩展、最佳实践 |
| Step 11 | [实战案例 —— 一个完整的对话流程](steps/step-11-practical-example.md) | 通过真实例子串联完整工作流 |
| Step 12 | [Agent 开发与测试指南](steps/step-12-agent-development-testing.md) | 如何开发、测试和验证自定义 Agent |

### 深入问答与生动解析

| 文档 | 内容 |
|------|------|
| [实验性工具、子 Task、MCP 上下文管理](./qa-experimental-tools-task-mcp.md) | 5 个实验性工具详解、子 Task 执行时机、大量 Tools/Skills/MCPs 的上下文空间管理 |
| [主循环生动解析（餐厅比喻）](./main-loop-visual-guide.md) | 用餐厅服务的比喻彻底理解主循环 |
| [主循环深度解析：停止条件与迭代机制](./qa-main-loop-deep-dive.md) | 停止主循环的底层原理、Prompt 在迭代中的变化 |
| [Subagent 深度解析（外包团队比喻）](./subagent-deep-dive.md) | Task 工具调用机制、Subagent 隔离运行原理、完整工作流程示例 |
| [Subagent Prompt 设计详解](./subagent-prompts.md) | Task Tool 提示词、Explore/General Agent 系统 Prompt、四层 Prompt 组装架构 |
| [Anthropic Prompt 深度解析](./prompt-anthropic-deep-dive.md) | 工业级 Prompt Engineering 典范：身份锚定、否定强化、极端示例、行为控制艺术 |
| [Agent vs Skill vs Tool vs MCP 设计指南](./agent-skill-tool-mcp-guide.md) | 四种扩展机制的边界与选择：何时派团队、何时请专家、何时用工具、何时叫外卖 |

### 待思考项

| 文档 | 内容 |
|------|------|
| [待思考项记录](./todo-thinking-items.md) | BatchTool 实现、Tools/Skills/MCPs 提示词规划策略 |

---

## 工作流全景图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           OpenCode 主工作流                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   用户输入                                                                        │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 1: 用户输入处理                                                    │  │
│   │ - 解析 message-v2 格式                                                  │  │
│   │ - 处理 text/file/agent/mcp_resource parts                               │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 2: Agent 选择                                                      │  │
│   │ - 解析 @agent_name 或 message.agent 字段                                 │  │
│   │ - 匹配 Agent 配置（name/description/model）                              │  │
│   │ - 应用 3 层权限合并（defaults/agent/user config）                        │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 3: 加载 Agent 配置                                                  │  │
│   │ - 合并 defaults/agent/session 三层配置                                   │  │
│   │ - 绑定到消息：agent、model、tools、permission                            │  │
│   │ - 处理 noReply 模式（hidden agent）                                      │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 4: 会话状态检查                                                     │  │
│   │ - 加载 Compaction/Prune 配置                                             │  │
│   │ - 检查 isOverflow（context - output - buffer）                           │  │
│   │ - 触发自动 Compaction                                                    │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 5: System Prompt 组装                                               │  │
│   │ - environment: 系统上下文（时间、目录、Project Rules、Git Status）         │  │
│   │ - skills: Agent 可用 Skill 列表                                          │  │
│   │ - instructions: Agent 专用指令                                           │  │
│   │ - reminders: 待办提醒（可选）                                            │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 6: Tool List 组装                                                   │  │
│   │ - ToolRegistry.all(): 获取所有工具                                       │  │
│   │ - resolveTools(): 过滤禁用工具 + MCP 合并                                │  │
│   │ - 模型特定过滤（apply_patch vs edit）                                    │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 7: 第一次 LLM 调用                                                  │  │
│   │ - streamText(): 流式调用                                                 │  │
│   │ - SessionProcessor: 事件处理（step-finish/tool-call）                    │  │
│   │ - Doom Loop 检测：3 次重复调用触发确认                                    │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 8: Tool 执行                                                        │  │
│   │ - 创建 Tool Part（status=pending）                                       │  │
│   │ - 更新为 running，执行 tool.execute()                                    │  │
│   │ - 2 层权限检查：external_directory + bash                                │  │
│   │ - 超时/取消处理（AbortSignal）                                           │  │
│   │ - 更新为 completed/error                                                 │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │ Step 9: User Content 组装和第二次 LLM 调用                               │  │
│   │ - MessageV2.toModelMessages(): 格式转换                                  │  │
│   │ - 特殊处理：媒体文件提取、Compaction 占位符                              │  │
│   │ - 第二次 LLM 调用，AI 基于 Tool Results 生成回复                         │  │
│   │ - 循环控制：结束或继续                                                   │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
│      │                                                                          │
│      ▼                                                                          │
│   返回结果给用户 / 继续循环                                                      │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 关键概念速查

### Agent 类型

| 类型 | 用途 | 可见性 |
|------|------|--------|
| `primary` | 用户对话 | 用户可见 |
| `subagent` | 子任务处理 | 用户可见（子会话） |
| `hidden` | 系统任务 | 用户不可见 |

### 权限层级

```
用户配置（opencode.yml）
      ↓ 覆盖
Agent 配置（Agent 定义）
      ↓ 覆盖
系统默认（src/agent/defaults.ts）
```

### 上下文管理机制

| 机制 | 触发条件 | 作用 |
|------|----------|------|
| **Prune** | 每次 step 后 | 删除 40K tokens 前的旧 tool outputs |
| **Compaction** | 上下文溢出时 | AI 生成对话摘要，替换历史消息 |

### 消息格式转换

```
Internal (MessageV2.WithParts) 
        ↓
    UI (UIMessage)
        ↓
   Model (ModelMessage)
```

---

## 后续计划

- [ ] BatchTool 实现分析
- [ ] Tools/Skills/MCPs 提示词规划策略
- [ ] 其他组件文档（Session、Provider 等）
