# 深入问题解答：实验性工具、子 Task 执行时机、上下文空间管理

## 1. 有哪些实验性的 tool？作用是什么？

### 实验性工具列表

| 工具 | 启用条件 | 作用 |
|------|----------|------|
| **LspTool** | `OPENCODE_EXPERIMENTAL_LSP_TOOL=1` | LSP (Language Server Protocol) 支持，提供代码导航功能 |
| **BatchTool** | `config.experimental.batch_tool: true` | 批量并行执行多个工具调用 |
| **PlanExitTool** | `OPENCODE_EXPERIMENTAL_PLAN_MODE=1` + CLI 客户端 | Plan 模式下退出 |
| **Bash 超时** | `OPENCODE_EXPERIMENTAL_BASH_DEFAULT_TIMEOUT_MS` | 自定义 bash 命令默认超时时间 |
| **Primary Tools** | `config.experimental.primary_tools` | 仅限主 Agent 使用的工具 |

### 详细说明

#### 1.1 LspTool - 语言服务器协议支持

```typescript
// packages/opencode/src/tool/lsp.ts

export const LspTool = Tool.define("lsp", {
  description: DESCRIPTION,
  parameters: z.object({
    operation: z.enum([
      "goToDefinition",      // 跳转到定义
      "findReferences",      // 查找引用
      "hover",               // 悬停提示
      "documentSymbol",      // 文档符号
      "workspaceSymbol",     // 工作区符号
      "goToImplementation",  // 跳转到实现
      "prepareCallHierarchy",// 调用层次
      "incomingCalls",       //  incoming 调用
      "outgoingCalls",       // outgoing 调用
    ]),
    filePath: z.string(),
    line: z.number(),       // 行号（1-based）
    character: z.number(),  // 列号（1-based）
  }),
})
```

**作用**：让 OpenCode 能够利用 VS Code 等编辑器的语言服务器，提供更精准的代码导航和理解能力。

**使用场景**：
```
AI: "让我查看这个函数的定义"
→ 调用 lsp({ operation: "goToDefinition", filePath: "src/utils.ts", line: 10, character: 5 })
```

#### 1.2 BatchTool - 批量工具执行

```typescript
// packages/opencode/src/tool/batch.ts

export const BatchTool = Tool.define("batch", {
  parameters: z.object({
    tool_calls: z.array(
      z.object({
        tool: z.string(),       // 工具名称
        parameters: z.object({}), // 工具参数
      })
    ).min(1).max(25),  // 最多 25 个
  }),
})
```

**作用**：允许 AI 在一个请求中并行执行多个工具，提高效率。

**使用场景**：
```json
{
  "tool": "batch",
  "input": {
    "tool_calls": [
      { "tool": "read", "parameters": { "filePath": "src/a.ts" } },
      { "tool": "read", "parameters": { "filePath": "src/b.ts" } },
      { "tool": "read", "parameters": { "filePath": "src/c.ts" } }
    ]
  }
}
```

**限制**：
- 最多 25 个工具调用
- 不能嵌套 batch（BatchTool 本身不能在 batch 中）
- 不能调用外部工具（MCP、环境工具）

#### 1.3 PlanExitTool - Plan 模式退出

```typescript
// 仅 CLI 客户端且启用实验性 Plan 模式时可用

export const PlanExitTool = Tool.define("plan_exit", {
  // 允许从 plan 模式退出
})
```

**作用**：在 Plan 模式（只读分析模式）中，允许 AI 主动退出回到 build 模式。

#### 1.4 实验性配置启用方式

```yaml
# ~/.opencode/opencode.yml

experimental:
  batch_tool: true           # 启用 BatchTool
  primary_tools:             # 仅限主 Agent 的工具
    - "dangerous_command"

# 或通过环境变量
# OPENCODE_EXPERIMENTAL_LSP_TOOL=1
# OPENCODE_EXPERIMENTAL_PLAN_MODE=1
# OPENCODE_EXPERIMENTAL_BASH_DEFAULT_TIMEOUT_MS=300000
```

---

## 2. 子 Task 执行的时机是什么？

### 触发条件

子 Task（Subtask）在以下时机执行：

```
主循环 loop() 每次迭代时
    │
    ▼
检查消息历史中的 subtask parts
    │
    ▼
如果有待处理的 subtask → 执行
```

### 代码位置

```typescript
// packages/opencode/src/session/prompt.ts 第 306-430 行

// 1. 从历史消息中收集 subtask
for (let i = msgs.length - 1; i >= 0; i--) {
  const msg = msgs[i]
  // ...
  const task = msg.parts.filter((part) => part.type === "compaction" || part.type === "subtask")
  if (task && !lastFinished) {
    tasks.push(...task)
  }
}

// 2. 如果最后一条消息是 subtask，执行它
const task = tasks.pop()

if (task?.type === "subtask") {
  const taskTool = await TaskTool.init()
  
  // 创建 Assistant 消息来承载 Task 执行
  const assistantMessage = await Session.updateMessage({
    id: MessageID.ascending(),
    role: "assistant",
    parentID: lastUser.id,
    sessionID,
    mode: task.agent,
    agent: task.agent,
    // ...
  })
  
  // 创建 Tool Part
  const part = await Session.updatePart({
    type: "tool",
    tool: TaskTool.id,
    state: {
      status: "running",
      input: {
        prompt: task.prompt,
        description: task.description,
        subagent_type: task.agent,
        command: task.command,
      },
    },
  })
  
  // 执行 Task
  await taskTool.execute({
    description: task.description,
    prompt: task.prompt,
    subagent_type: task.agent,
    command: task.command,
  }, context)
}
```

### Subtask 的创建方式

#### 方式 1：用户通过 @ 提及

```
User: @explore 帮我搜索所有使用 User 模型的文件

系统：
1. 识别到 @explore
2. 创建 subtask part
3. 进入主循环，执行 explore Agent
```

代码位置：
```typescript
// packages/opencode/src/session/prompt.ts 第 1840-1858 行

parts.push({
  type: "subtask",
  agent: agent.name,
  description: command.description ?? "",
  command: input.command,
  model: { providerID, modelID },
  prompt: command.prompt,
})
```

#### 方式 2：AI 调用 Task 工具

```typescript
// packages/opencode/src/tool/task.ts

AI 调用 task({
  description: "搜索代码",
  prompt: "搜索所有使用 User 模型的文件",
  subagent_type: "explore",
})

系统：
1. 创建新的子会话
2. 使用 explore Agent 处理
3. 返回结果给父会话
```

### 执行流程图

```
用户输入: "@general 分析性能瓶颈"
         │
         ▼
创建 Subtask Part
{
  type: "subtask",
  agent: "general",
  prompt: "分析性能瓶颈",
  ...
}
         │
         ▼
进入主循环 loop()
         │
         ▼
检测到 subtask part
         │
         ▼
创建子会话 Session.create({
  parentID: 父会话ID,
  title: "分析性能瓶颈 (@general)"
})
         │
         ▼
调用 explore Agent 处理
         │
         ▼
返回结果给父会话
"发现以下性能问题：1. ... 2. ..."
```

### 子 Task 的权限限制

子 Task 有一些特殊的权限限制：

```typescript
// packages/opencode/src/tool/task.ts 第 76-101 行

return await Session.create({
  parentID: ctx.sessionID,
  title: params.description + ` (@${agent.name} subagent)`,
  permission: [
    // 子 Agent 不能操作 todo 列表
    { permission: "todowrite", pattern: "*", action: "deny" },
    { permission: "todoread", pattern: "*", action: "deny" },
    
    // 子 Agent 默认不能再创建子 Agent（防止无限递归）
    ...(hasTaskPermission ? [] : [{
      permission: "task",
      pattern: "*",
      action: "deny",
    }]),
    
    // 实验性：主 Agent 专属工具
    ...(config.experimental?.primary_tools?.map((t) => ({
      pattern: "*",
      action: "allow",
      permission: t,
    })) ?? []),
  ],
})
```

**限制原因**：
1. **不能操作 todo**：避免和主 Agent 的 todo 列表冲突
2. **不能创建子 Agent**：防止无限递归，除非特别配置

---

## 3. 大量的工具、skill、mcp 会挤占上下文空间吗？

### 简短回答

**会的**，但系统有相应的控制机制：

1. **工具描述会占用 token**
2. **Skill 描述默认不放入上下文**（需要时通过 skill 工具加载）
3. **MCP 工具有选择性地启用**
4. **有工具过滤和权限控制**

### 详细分析

#### 3.1 工具描述的长度

每个工具都有 description 和 parameters schema，这些都会转换为 JSON Schema 发送给 LLM：

```typescript
// 典型工具描述的长度
{
  "bash": {
    "description": "Execute shell commands... (~500 tokens)",
    "parameters": {
      "command": { "type": "string", "description": "..." },
      "timeout": { "type": "number", "description": "..." },
      // ...
    }
  }
}
```

**估算**：
- 每个内置工具：~200-500 tokens
- 10 个内置工具：~2000-5000 tokens
- MCP 工具：每个 ~100-300 tokens
- 大量 MCP 工具确实会占用显著空间

#### 3.2 控制机制

##### 机制 1：权限过滤（主要）

```typescript
// packages/opencode/src/session/prompt.ts 第 808-830 行

for (const t of allTools) {
  // 检查工具是否被 Agent 权限禁用
  const disabled = PermissionNext.disabled([t.id], input.agent.permission)
  if (disabled.has(t.id)) continue  // 跳过禁用的工具
  
  // 检查是否是主 Agent 专属工具
  if (isPrimaryOnlyTool(t.id) && input.agent.mode !== "primary") continue
  
  // 添加到可用工具列表
  tools[t.id] = tool({...})
}
```

**效果**：
- explore Agent 只有 8 个工具（而不是全部）
- plan Agent 没有 edit/write 工具
- 减少工具描述占用的 token

##### 机制 2：MCP 工具的选择性启用

```typescript
// 用户可以在配置中启用/禁用 MCP 服务器

// ~/.opencode/opencode.yml
mcp:
  servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    # 不在这里配置的服务器不会加载
```

**效果**：只有配置并启用的 MCP 服务器才会加载其工具。

##### 机制 3：Skill 的延迟加载

```typescript
// packages/opencode/src/session/system.ts 第 59-71 行

export async function skills(agent: Agent.Info) {
  // 检查是否有 skill 权限
  if (PermissionNext.disabled(["skill"], agent.permission).has("skill")) 
    return

  const list = await Skill.available(agent)
  
  return [
    "Skills provide specialized instructions...",
    "Use the skill tool to load a skill when a task matches its description.",
    Skill.fmt(list, { verbose: true }),  // 只列出名称和简短描述
  ].join("\n")
}
```

**关键点**：
- Skill **描述**不会默认加载到上下文
- 只有 Skill **列表**（名称+简介）会加载
- AI 需要通过 `skill` 工具显式加载具体的 skill

##### 机制 4：模型特定的工具过滤

```typescript
// packages/opencode/src/tool/registry.ts 第 142-155 行

.filter((t) => {
  // websearch/codesearch 只对特定 provider 可用
  if (t.id === "codesearch" || t.id === "websearch") {
    return model.providerID === ProviderID.opencode || Flag.OPENCODE_ENABLE_EXA
  }

  // GPT 模型使用 apply_patch 代替 edit/write
  const usePatch = model.modelID.includes("gpt-") 
    && !model.modelID.includes("oss") 
    && !model.modelID.includes("gpt-4")
  if (t.id === "apply_patch") return usePatch
  if (t.id === "edit" || t.id === "write") return !usePatch

  return true
})
```

**效果**：根据模型类型动态调整可用工具，避免不必要工具的占用。

#### 3.3 实际占用估算

**场景 A：标准 build Agent**
```
工具数量：~12 个
占用 token：~3000-5000 tokens (约 1.5-2.5% 的 200K 上下文)
影响：轻微
```

**场景 B：带 5 个 MCP 服务器的 build Agent**
```
内置工具：~12 个
MCP 工具：~20 个 (假设每个服务器 4 个工具)
总工具：~32 个
占用 token：~8000-12000 tokens (约 4-6% 的 200K 上下文)
影响：可接受
```

**场景 C：带大量 MCP 服务器（20 个）**
```
内置工具：~12 个
MCP 工具：~80 个 (假设每个服务器 4 个工具)
总工具：~92 个
占用 token：~25000-35000 tokens (约 12-17% 的 200K 上下文)
影响：显著，可能影响对话质量
```

#### 3.4 优化建议

如果工具太多导致上下文紧张：

##### 1. 使用 Agent 权限限制工具

```yaml
# ~/.opencode/opencode.yml

agent:
  my-custom-agent:
    name: "my-custom-agent"
    mode: "primary"
    permission:
      # 只允许必要工具
      "*": "deny"
      "read": "allow"
      "glob": "allow"
      "grep": "allow"
```

##### 2. 精简 MCP 服务器

只启用真正需要的 MCP 服务器，避免加载过多。

##### 3. 使用 Task 工具分担

```
复杂任务 → Task 工具 → 子 Agent
                    ↓
            子 Agent 有自己的工具集
            不会增加父会话的工具数量
```

##### 4. 监控 Token 使用

```typescript
// 在 finish-step 事件中检查
case "finish-step":
  const usage = Session.getUsage({...})
  console.log(`Tools token usage: ${usage.tokens.input} input, ${usage.tokens.output} output`)
```

### 总结

| 问题 | 答案 |
|------|------|
| 工具会占用上下文吗？ | **会**，每个工具描述 ~200-500 tokens |
| Skill 会占用上下文吗？ | **轻微**，只加载列表，不加载详细描述 |
| MCP 会占用上下文吗？ | **会**，且取决于 MCP 服务器数量 |
| 如何控制？ | 权限过滤、模型过滤、选择性启用 MCP、Task 分担 |
| 建议上限？ | **总工具数 < 50**（约 10K-15K tokens）|
