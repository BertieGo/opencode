# Step 6: 组装可用工具列表 —— AI 的"工具箱检查"

> **一句话总结**：根据 Agent 的权限配置，从工具注册表中筛选出允许使用的工具，并为每个工具创建可执行的函数实例。

---

## 🎬 场景回顾

前五步完成了：
1. ✅ **Step 1**：用户消息已打包
2. ✅ **Step 2**：确定使用 build Agent
3. ✅ **Step 3**：Agent 配置绑定到会话
4. ✅ **Step 4**：检查并压缩会话状态
5. ✅ **Step 5**：组装 System Prompt

现在 AI 已经有了"入职手册"，接下来要给它准备**"工具箱"**——告诉它有哪些工具可以用。

---

## 🧰 工具系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     OpenCode 工具系统                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 ToolRegistry（工具注册表）                │   │
│  │                                                          │   │
│  │  内置工具                     条件/实验性工具             │   │
│  │  ┌─────────────┐             ┌─────────────────────┐     │   │
│  │  │ bash        │             │ QuestionTool        │     │   │
│  │  │ read        │             │ LspTool (实验)      │     │   │
│  │  │ write       │             │ BatchTool (实验)    │     │   │
│  │  │ edit        │             │ PlanExitTool (CLI)  │     │   │
│  │  │ glob        │             └─────────────────────┘     │   │
│  │  │ grep        │                                          │   │
│  │  │ task        │             自定义工具                    │   │
│  │  │ webfetch    │             ┌─────────────────────┐     │   │
│  │  │ websearch   │             │ 插件工具             │     │   │
│  │  │ codesearch  │             │ 自定义 tool 文件     │     │   │
│  │  │ todo        │             └─────────────────────┘     │   │
│  │  │ skill       │                                          │   │
│  │  └─────────────┘                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              resolveTools()（权限过滤）                  │   │
│  │                                                          │   │
│  │  输入：所有可用工具 + Agent 权限配置                      │   │
│  │  输出：过滤后的工具列表                                   │   │
│  │                                                          │   │
│  │  规则：                                                   │   │
│  │  - "*": "allow"  →  允许所有                             │   │
│  │  - "bash": "deny" →  禁止 bash                           │   │
│  │  - "read": "ask"  →  需要确认                            │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              AI SDK 工具格式                             │   │
│  │                                                          │   │
│  │  {                                                       │   │
│  │    "bash": {                                             │   │
│  │      description: "执行 shell 命令",                      │   │
│  │      parameters: { ... }                                 │   │
│  │    },                                                    │   │
│  │    "read": { ... },                                      │   │
│  │    ...                                                   │   │
│  │  }                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 内置工具清单

OpenCode 内置了以下工具：

| 工具 | ID | 用途 | 说明 |
|------|-----|------|------|
| **Bash** | `bash` | 执行 shell 命令 | 运行测试、安装依赖等 |
| **Read** | `read` | 读取文件内容 | 查看源码、配置文件 |
| **Write** | `write` | 写入新文件 | 创建新文件 |
| **Edit** | `edit` | 编辑现有文件 | 修改代码 |
| **Glob** | `glob` | 文件模式匹配 | 找文件如 `src/**/*.ts` |
| **Grep** | `grep` | 代码搜索 | 搜索特定文本或模式 |
| **Task** | `task` | 召唤子 Agent | 并行执行子任务 |
| **WebFetch** | `webfetch` | 获取网页内容 | 读取 URL |
| **WebSearch** | `websearch` | 网络搜索 | 搜索信息（需配置）|
| **CodeSearch** | `codesearch` | 代码搜索 | 语义搜索代码（需配置）|
| **TodoWrite** | `todowrite` | 写入待办 | 管理任务列表 |
| **Skill** | `skill` | 加载技能 | 使用专业领域技能 |
| **ApplyPatch** | `apply_patch` | 应用补丁 | GPT 专用补丁格式 |
| **Invalid** | `invalid` | 无效工具占位 | 用于错误处理 |

### 条件启用的工具

| 工具 | 启用条件 |
|------|----------|
| **QuestionTool** | CLI/App/Desktop 客户端，或启用环境变量 |
| **LspTool** | `OPENCODE_EXPERIMENTAL_LSP_TOOL=1` |
| **BatchTool** | 配置 `experimental.batch_tool: true` |
| **PlanExitTool** | CLI 客户端且启用 Plan 模式 |

---

## 🔧 工具注册表（ToolRegistry）

### 初始化过程

```typescript
// packages/opencode/src/tool/registry.ts 第 38-63 行

export const state = Instance.state(async () => {
  const custom = [] as Tool.Info[]

  // 1. 扫描配置目录中的自定义工具
  const matches = await Config.directories().then((dirs) =>
    dirs.flatMap((dir) =>
      Glob.scanSync("{tool,tools}/*.{js,ts}", { 
        cwd: dir, 
        absolute: true, 
        dot: true, 
        symlink: true 
      }),
    ),
  )
  
  // 加载自定义工具文件
  for (const match of matches) {
    const namespace = path.basename(match, path.extname(match))
    const mod = await import(pathToFileURL(match).href)
    for (const [id, def] of Object.entries<ToolDefinition>(mod)) {
      custom.push(fromPlugin(id === "default" ? namespace : `${namespace}_${id}`, def))
    }
  }

  // 2. 加载插件注册的工具
  const plugins = await Plugin.list()
  for (const plugin of plugins) {
    for (const [id, def] of Object.entries(plugin.tool ?? {})) {
      custom.push(fromPlugin(id, def))
    }
  }

  return { custom }
})
```

### 获取所有工具

```typescript
// packages/opencode/src/tool/registry.ts 第 99-126 行

async function all(): Promise<Tool.Info[]> {
  const custom = await state().then((x) => x.custom)
  const config = await Config.get()
  
  // 检查是否需要启用 QuestionTool
  const question = ["app", "cli", "desktop"].includes(Flag.OPENCODE_CLIENT) 
    || Flag.OPENCODE_ENABLE_QUESTION_TOOL

  return [
    InvalidTool,                    // 无效工具占位
    ...(question ? [QuestionTool] : []),
    BashTool,                       // 核心工具
    ReadTool,
    GlobTool,
    GrepTool,
    EditTool,
    WriteTool,
    TaskTool,                       // 子 Agent
    WebFetchTool,
    TodoWriteTool,                  // 任务管理
    // TodoReadTool,                // 已禁用
    WebSearchTool,                  // 搜索（需配置）
    CodeSearchTool,
    SkillTool,                      // 技能系统
    ApplyPatchTool,                 // GPT 补丁
    ...(Flag.OPENCODE_EXPERIMENTAL_LSP_TOOL ? [LspTool] : []),
    ...(config.experimental?.batch_tool === true ? [BatchTool] : []),
    ...(Flag.OPENCODE_EXPERIMENTAL_PLAN_MODE && Flag.OPENCODE_CLIENT === "cli" 
      ? [PlanExitTool] : []),
    ...custom,                      // 自定义工具
  ]
}
```

### 模型特定的工具过滤

```typescript
// packages/opencode/src/tool/registry.ts 第 132-173 行

export async function tools(model, agent) {
  const tools = await all()
  
  const result = await Promise.all(
    tools
      .filter((t) => {
        // 1. websearch/codesearch 只对 opencode provider 或启用标志的用户可用
        if (t.id === "codesearch" || t.id === "websearch") {
          return model.providerID === ProviderID.opencode 
            || Flag.OPENCODE_ENABLE_EXA
        }

        // 2. GPT 模型使用 apply_patch 代替 edit/write
        const usePatch = model.modelID.includes("gpt-") 
          && !model.modelID.includes("oss") 
          && !model.modelID.includes("gpt-4")
        if (t.id === "apply_patch") return usePatch
        if (t.id === "edit" || t.id === "write") return !usePatch

        return true
      })
      .map(async (t) => {
        // 初始化工具，获取描述和参数定义
        const tool = await t.init({ agent })
        return {
          id: t.id,
          description: tool.description,
          parameters: tool.parameters,
          execute: tool.execute,
        }
      }),
  )
  return result
}
```

---

## 🛡️ 权限过滤（resolveTools）

工具准备好了，但要根据 Agent 的权限配置来**过滤**。

### 主过滤逻辑

```typescript
// packages/opencode/src/session/prompt.ts 第 743-850 行

export async function resolveTools(input: {
  agent: Agent.Info
  model: Provider.Model
  session: Session.Info
  tools?: Record<string, boolean>
  processor: SessionProcessor.Info
  bypassAgentCheck: boolean
  messages: MessageV2.WithParts[]
}) {
  const tools: Record<string, AITool> = {}

  // 1. 创建工具上下文（每个工具执行时会用到）
  const context = (args: any, options: ToolCallOptions): Tool.Context => ({
    sessionID: input.session.id,
    abort: options.abortSignal!,
    messageID: input.processor.message.id,
    callID: options.toolCallId,
    extra: { model: input.model, bypassAgentCheck: input.bypassAgentCheck },
    agent: input.agent.name,
    messages: input.messages,
    metadata: async (val) => { /* 更新工具执行元数据 */ },
    ask: async (req) => { /* 权限询问 */ },
  })

  // 2. 从注册表获取所有可用工具
  const registered = await ToolRegistry.tools(
    { providerID: input.model.providerID, modelID: input.model.api.id },
    input.agent,
  )

  // 3. 合并 MCP 工具
  const mcp = await MCP.list()
  const allTools = [
    ...registered,
    ...mcp.flatMap((client) =>
      Object.entries(client.tools).map(([name, t]) => ({
        id: `${client.name}_${name}`,
        description: t.description,
        parameters: t.parameters,
      })),
    ),
  ]

  // 4. 根据权限过滤工具
  for (const t of allTools) {
    const disabled = PermissionNext.disabled([t.id], input.agent.permission)
    
    // 检查工具是否被禁用
    if (disabled.has(t.id)) continue
    
    // 检查是否是主 Agent 专属工具
    if (/* 检查 primary_tools 配置 */) continue

    // 5. 创建 AI SDK 格式的工具
    tools[t.id] = tool({
      description: t.description,
      parameters: t.parameters,
      execute: async (args, options) => {
        // 实际执行工具...
      },
    })
  }

  return tools
}
```

### 权限检查详解

```typescript
// packages/opencode/src/session/llm.ts 第 258-266 行

async function resolveTools(input) {
  // 根据 Agent 权限找出被禁用的工具
  const disabled = PermissionNext.disabled(
    Object.keys(input.tools), 
    input.agent.permission
  )
  
  for (const tool of Object.keys(input.tools)) {
    // 检查：1. 用户消息中明确禁用，或 2. Agent 权限中禁用
    if (input.user.tools?.[tool] === false || disabled.has(tool)) {
      delete input.tools[tool]  // 从列表中移除
    }
  }
  
  return input.tools
}
```

**权限规则示例**：

```typescript
// build Agent 的权限配置
{
  "*": "allow",           // 默认允许所有
  "bash": "allow",        // 明确允许 bash
  "edit": "allow",        // 明确允许 edit
  "question": "allow",    // 允许提问
}

// plan Agent 的权限配置
{
  "*": "allow",
  "edit": { "*": "deny" },  // ⭐ 禁止所有编辑！
  "write": { "*": "deny" }, // ⭐ 禁止写入！
  "question": "allow",
}

// explore Agent 的权限配置
{
  "*": "deny",            // ⭐ 先全部禁止
  "grep": "allow",        // 只允许搜索类
  "glob": "allow",
  "read": "allow",
  "bash": "allow",
}
```

---

## 🔄 工具执行流程

当 AI 决定调用工具时：

```
AI 输出 tool-call
       │
       ▼
┌─────────────────┐
│  解析工具调用    │
│  - 工具 ID      │
│  - 参数         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  检查权限        │
│  - 是否允许？   │
│  - 需要询问？   │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
  允许       询问用户
    │         │
    ▼         ▼
┌─────────────────┐
│  执行工具        │
│  - 调用 execute │
│  - 获取结果     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  返回结果给 AI   │
│  (tool-result)  │
└─────────────────┘
```

---

## 🎯 形象比喻：工具箱检查

| 现实场景 | OpenCode Step 6 |
|---------|----------------|
| 准备工具箱 | ToolRegistry.all() |
| 检查公司标准工具 | 内置工具列表 |
| 检查个人定制工具 | 自定义 tool 文件 |
| 检查特殊工具许可 | 权限过滤 |
| 某些工具需要审批 | "ask" 权限 |
| 某些工具禁止使用 | "deny" 权限 |
| 工具装箱 | resolveTools() |
| 工具清单给工人 | AI SDK 格式 |

**完整场景**：

> 快递员张三（build Agent）准备出发，仓库管理员（resolveTools）给他准备工具箱：
> 
> 1. **基础工具**（必带）：bash、read、write、edit —— 这些是核心工作工具
> 2. **搜索工具**：glob、grep、webfetch —— 用于查找信息
> 3. **管理工具**：todowrite —— 用于任务管理
> 4. **召唤工具**：task —— 可以召唤小弟帮忙
> 5. **权限检查**：管理员检查张三的许可证
>    - ✅ bash: allow —— 可以用
>    - ✅ read: allow —— 可以用
>    - ❌ docker: deny —— 不能用（plan Agent 可能禁止）
>    - ⚠️ edit: ask —— 需要用户确认才能用
>
> 最后，管理员把允许使用的工具清单交给张三，他开始工作！

---

## 💡 关键设计思想

### 1. 工具与权限分离
- **ToolRegistry**：只关心"有什么工具"
- **Agent 权限**：只关心"能用哪些工具"
- **resolveTools**：将两者结合

### 2. 动态加载
- 自定义工具可以从配置文件目录加载
- 插件可以注册新工具
- 支持热更新（通过 Instance.state）

### 3. 模型适配
- GPT 使用 `apply_patch` 而不是 `edit`/`write`
- 某些工具只在特定客户端可用
- 搜索工具需要特殊权限

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| 工具注册表 | `packages/opencode/src/tool/registry.ts` | 35-126 |
| 获取所有工具 | `packages/opencode/src/tool/registry.ts` | 99-126 |
| 模型特定过滤 | `packages/opencode/src/tool/registry.ts` | 132-173 |
| 权限过滤 | `packages/opencode/src/session/prompt.ts` | 743-850 |
| 简化权限检查 | `packages/opencode/src/session/llm.ts` | 258-266 |
| 工具执行上下文 | `packages/opencode/src/tool/tool.ts` | - |

---

## 🚀 下一步

完成 Step 6 后，系统已经：
1. ✅ 准备了所有可用工具
2. ✅ 根据 Agent 权限过滤
3. ✅ 转换为 AI SDK 格式

接下来进入 **Step 7: 第一次调用 LLM**——真正开始和 AI 对话！

准备好进入 **Step 7** 了吗？
