# Subagent Prompt 设计详解

> 深入分析 OpenCode 中 Subagent 的系统 Prompt 是如何设计和组装的

---

## 一、整体架构：三层 Prompt 叠加

```
┌─────────────────────────────────────────────────────────────────┐
│                    System Prompt 组装顺序                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ 第 1 层：Agent 专属 Prompt                                │   │
│   │ (如果有 agent.prompt，否则用 Provider 默认)               │   │
│   │                                                          │   │
│   │ explore agent:                                           │   │
│   │ "You are a file search specialist..."                    │   │
│   │                                                          │   │
│   │ general agent:                                           │   │
│   │ (无，使用 Provider 默认提示)                              │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ 第 2 层：环境信息 (SystemPrompt.environment)              │   │
│   │                                                          │   │
│   │ - 当前时间                                               │   │
│   │ - 工作目录                                               │   │
│   │ - 你是谁 (OpenCode)                                      │   │
│   │ - 最佳实践链接                                           │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ 第 3 层：项目指令 (InstructionPrompt.system)              │   │
│   │                                                          │   │
│   │ - AGENTS.md 内容                                         │   │
│   │ - CLAUDE.md 内容                                         │   │
│   │ - 用户自定义 instructions                                │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ 第 4 层：Skills 信息 (如果需要)                           │   │
│   │ "You have access to the following skills..."             │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**关键代码位置**：`packages/opencode/src/session/llm.ts:72`

```typescript
const system = [
  // 第 1 层：Agent 专属 Prompt
  ...(input.agent.prompt ? [input.agent.prompt] : isCodex ? [] : SystemPrompt.provider(input.model)),
  // 第 2/3/4 层：其他 System Prompt
  ...input.system,
  ...input.user.system,
]
```

---

## 二、Task Tool：告诉主 Agent 何时使用 Subagent

**文件位置**：`packages/opencode/src/tool/task.txt`

```
Launch a new agent to handle complex, multistep tasks autonomously.

Available agent types and the tools they have access to:
{agents}  ← 动态插入可用的 agent 列表

When using the Task tool, you must specify a subagent_type parameter to select which agent type to use.

When to use the Task tool:
- When you are instructed to execute custom slash commands. Use the Task tool with the slash command invocation as the entire prompt. For example: Task(description="Check the file", prompt="/check-file path/to/file.py")

When NOT to use the Task tool:
- If you want to read a specific file path, use the Read or Glob tool instead of the Task tool, to find the match more quickly
- If you are searching for a specific class definition like "class Foo", use the Glob tool instead, to find the match more quickly
- If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead, to find the match more quickly
- Other tasks that are not related to the agent descriptions above


Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result. The output includes a task_id you can reuse later to continue the same subagent session.
3. Each agent invocation starts with a fresh context unless you provide task_id to resume the same subagent session (which continues with its previous messages and tool outputs). When starting fresh, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted
5. Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent. Tell it how to verify its work if possible (e.g., relevant test commands).
6. If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first. Use your judgement.
```

### 关键设计要点

| 设计元素 | 目的 |
|---------|------|
| **Launch a new agent** | 明确这是一个"启动新代理"的工具 |
| **{agents} 占位符** | 动态插入可用 agent 类型及其描述 |
| **When to use / When NOT to use** | 明确的边界条件，防止滥用 |
| **Usage notes** | 详细的使用指南，强调并行、信任、详细描述等 |

---

## 三、Explore Agent：只读代码探索专员

**文件位置**：`packages/opencode/src/agent/prompt/explore.txt`

```
You are a file search specialist. You excel at thoroughly navigating and exploring codebases.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Use Read when you know the specific file path you need to read
- Use Bash for file operations like copying, moving, or listing directory contents
- Adapt your search approach based on the thoroughness level specified by the caller
- Return file paths as absolute paths in your final response
- For clear communication, avoid using emojis
- Do not create any files, or run bash commands that modify the user's system state in any way

Complete the user's search request efficiently and report your findings clearly.
```

### Prompt 设计分析

| 设计元素 | 目的 |
|---------|------|
| **file search specialist** | 明确定位：专门搜索文件，不写代码 |
| **Your strengths** | 列举能力边界，强化自我认知 |
| **Guidelines** | 工具选择指导：何时用 Glob、Grep、Read |
| **avoid using emojis** | 输出规范：保持专业简洁 |
| **Do not create any files** | 严格限制：只读，不修改 |

### Explore Agent 的权限配置（代码级）

```typescript
// packages/opencode/src/agent/agent.ts:131-157
explore: {
  name: "explore",
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      "*": "deny",           // 默认禁止所有
      grep: "allow",         // ✅ 允许搜索
      glob: "allow",         // ✅ 允许查找文件
      list: "allow",         // ✅ 允许列出目录
      bash: "allow",         // ✅ 允许执行命令
      webfetch: "allow",     // ✅ 允许网页抓取
      websearch: "allow",    // ✅ 允许网络搜索
      codesearch: "allow",   // ✅ 允许代码搜索
      read: "allow",         // ✅ 允许读取文件
      // ❌ 没有 edit/write！
    }),
    user,
  ),
  description: `Fast agent specialized for exploring codebases...`,
  prompt: PROMPT_EXPLORE,  // ← 上面的 explore.txt
  mode: "subagent",        // ← 标记为 subagent
}
```

---

## 四、General Agent：通用研究员

**Prompt 设计**：General agent **没有自定义 prompt**，使用默认 Provider Prompt

```typescript
// packages/opencode/src/agent/agent.ts:116-130
general: {
  name: "general",
  description: `General-purpose agent for researching complex questions and executing multi-step tasks.`,
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      todoread: "deny",    // ❌ 禁止读取主任务列表
      todowrite: "deny",   // ❌ 禁止修改主任务列表
    }),
    user,
  ),
  options: {},
  mode: "subagent",
  // 注意：没有 prompt 字段！使用默认 Provider Prompt
}
```

### 默认 Provider Prompt 示例（Anthropic）

**文件位置**：`packages/opencode/src/session/prompt/anthropic.txt`

```
You are an elite software engineer...（详细的角色定义）

When providing code changes:
- Use the StrReplaceFile tool for concise, surgical edits...
- Prefer functional array methods...
- Avoid unnecessary destructuring...
```

**设计意图**：
- General agent 拥有接近主 Agent 的能力
- 只是禁止了 todo 工具（避免干扰主任务列表）
- 使用标准编码规范，适合复杂多步骤任务

---

## 五、Subagent 执行时的完整 Prompt 组装

### 调用链

```
Task Tool Execute
       │
       ▼
SessionPrompt.prompt()  ← 创建 sub session
       │
       ▼
SessionPrompt.loop()    ← 启动主循环
       │
       ▼
LLM.stream()            ← 组装 Prompt
       │
       ▼
实际调用 AI API
```

### 代码流程

```typescript
// 1. Task Tool 执行时 (task.ts:129-144)
const result = await SessionPrompt.prompt({
  messageID,
  sessionID: session.id,     // ← 新的 sub session
  model: { modelID, providerID },
  agent: agent.name,         // ← "explore" 或 "general"
  tools: {
    todowrite: false,        // ← 禁用 todo
    todoread: false,
    ...(hasTaskPermission ? {} : { task: false }),  // ← 禁用嵌套 task
  },
  parts: promptParts,        // ← 用户的任务描述
})

// 2. 创建用户消息时 (prompt.ts:963-964)
const agent = await Agent.get(input.agent ?? "build")

// 3. LLM 调用时组装 Prompt (llm.ts:67-80)
const system = [
  // 第 1 层：Agent 专属 Prompt (explore.txt 或默认)
  ...(input.agent.prompt ? [input.agent.prompt] : SystemPrompt.provider(model)),
  
  // 第 2/3 层：环境和项目指令
  ...input.system,           // SystemPrompt.environment + InstructionPrompt.system
  
  // 第 4 层：用户自定义
  ...(input.user.system ? [input.user.system] : []),
]
```

---

## 六、实际场景：Explore Agent 收到的完整 Prompt

### 场景：用户输入 `@explore 找出所有使用 useState 的组件`

### Explore Agent 收到的 System Prompt：

```
┌─────────────────────────────────────────────────────────────────┐
│                      System Prompt                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ 【第 1 层】Agent 专属 Prompt (explore.txt):                      │
│ ─────────────────────────────────────                          │
│ You are a file search specialist. You excel at thoroughly      │
│ navigating and exploring codebases.                            │
│                                                                │
│ Your strengths:                                                │
│ - Rapidly finding files using glob patterns                    │
│ - Searching code and text with powerful regex patterns         │
│ - Reading and analyzing file contents                          │
│                                                                │
│ Guidelines:                                                    │
│ - Use Glob for broad file pattern matching                     │
│ - Use Grep for searching file contents with regex              │
│ - ...                                                          │
│ - Do not create any files...                                   │
│                                                                │
│ 【第 2 层】环境信息:                                            │
│ ─────────────────                                                  │
│ You are OpenCode, an expert coding assistant...                │
│ Current time: 2025-03-17 10:30:00                              │
│ Current working directory: /Users/project                      │
│                                                                │
│ 【第 3 层】项目指令 (AGENTS.md):                                │
│ ───────────────────────                                          │
│ - ALWAYS USE PARALLEL TOOLS WHEN APPLICABLE                    │
│ - Prefer single word variable names                            │
│ ...                                                              │
│                                                                │
└─────────────────────────────────────────────────────────────────┘
```

### Explore Agent 收到的 User Message：

```
找出所有使用 useState 的组件
```

### Explore Agent 的可用工具：

```typescript
{
  grep:    { enabled: true },   // ✅
  glob:    { enabled: true },   // ✅
  read:    { enabled: true },   // ✅
  bash:    { enabled: true },   // ✅
  edit:    { enabled: false },  // ❌
  write:   { enabled: false },  // ❌
  task:    { enabled: false },  // ❌ 不能再创建 subagent
  todowrite: { enabled: false },// ❌
  todoread:  { enabled: false },// ❌
}
```

---

## 七、Prompt 设计的关键原则

### 1. **角色明确化**

```
❌ 差："你是一个 AI 助手"
✅ 好："You are a file search specialist"
```

### 2. **能力边界清晰**

```
Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents
```

### 3. **工具使用指导**

```
Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Use Read when you know the specific file path
```

### 4. **限制条件明确**

```
- Do not create any files
- Do not run bash commands that modify the system
- Avoid using emojis
```

### 5. **输出格式规范**

```
- Return file paths as absolute paths
- Report your findings clearly
```

---

## 八、总结对比表

| Agent 类型 | 专属 Prompt | 主要权限 | 用途 |
|-----------|-------------|---------|------|
| **build** | Provider 默认 | 完整权限 | 主 Agent |
| **explore** | `explore.txt` | 只读 (grep/glob/read/bash) | 代码探索 |
| **general** | Provider 默认 | 接近完整，禁止 todo | 通用研究 |
| **plan** | `plan.txt` | 禁止 edit | 规划模式 |
| **compaction** | `compaction.txt` | 几乎无权限 | 生成摘要 |
| **title** | `title.txt` | 无工具 | 生成标题 |

---

**关键洞察**：Subagent 的 Prompt 设计核心是**"限制即能力"**——通过明确的角色定义和权限限制，让每个 subagent 专注于特定任务，从而提高整体效率和可靠性。 🎯
