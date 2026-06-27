# Step 1: 用户输入处理 —— 快递分拣中心的故事

> **一句话总结**：用户输入处理就是把用户的"一句话"包装成一个**结构化的消息对象**，贴上**完整的元数据标签**，然后**存入数据库**，准备进入下一步的主循环。

---

## 🎬 场景设定

想象一下，你在 OpenCode 的聊天框里输入了一句话：

```
我运行 `bun test` 报错了，帮我修复。错误信息说 `sum` 函数返回了 undefined。
```

这句话踏上了一段奇妙的旅程...

---

## 📦 第一站：快递收件口

当用户按下回车键，输入首先到达 `SessionPrompt.prompt()` 函数。这就像快递到达分拣中心的第一步——**收件登记**。

### 入口代码

```typescript
// packages/opencode/src/session/prompt.ts 第 160-187 行

export const prompt = fn(PromptInput, async (input) => {
  // 1. 获取当前会话
  const session = await Session.get(input.sessionID)
  
  // 2. 清理可能存在的恢复点（防止回退冲突）
  await SessionRevert.cleanup(session)

  // 3. ⭐ 核心：创建用户消息对象（Step 1 的重点！）
  const message = await createUserMessage(input)
  
  // 4. 更新会话的"最后活动时间"
  await Session.touch(input.sessionID)

  // 5. 处理旧版的工具权限配置（兼容代码）
  const permissions: PermissionNext.Ruleset = []
  for (const [tool, enabled] of Object.entries(input.tools ?? {})) {
    permissions.push({
      permission: tool,
      action: enabled ? "allow" : "deny",
      pattern: "*",
    })
  }
  if (permissions.length > 0) {
    session.permission = permissions
    await Session.setPermission({ sessionID: session.id, permission: permissions })
  }

  // 6. 如果设置了 noReply，只保存消息不进入主循环
  if (input.noReply === true) {
    return message
  }

  // 7. 进入主循环（这是下一步的事情了）
  return loop({ sessionID: input.sessionID })
})
```

### 输入的数据结构

用户输入被包装成 `PromptInput` 对象：

```typescript
// packages/opencode/src/session/prompt.ts 第 93-158 行

export const PromptInput = z.object({
  sessionID: SessionID.zod,           // 会话ID，告诉系统这是哪个对话
  messageID: MessageID.zod.optional(), // 消息ID（可选，系统自动生成）
  model: z.object({                   // 指定使用的AI模型（可选）
    providerID: ProviderID.zod,       // 如："anthropic"
    modelID: ModelID.zod,             // 如："claude-3-5-sonnet"
  }).optional(),
  agent: z.string().optional(),       // 指定使用哪个Agent（如："build"）
  noReply: z.boolean().optional(),    // 是否不进入主循环（纯保存消息）
  parts: z.array(                     // ⭐ 用户发送的内容块数组
    z.discriminatedUnion("type", [
      // 文字内容
      MessageV2.TextPart.omit({ messageID: true, sessionID: true }),
      // 文件附件
      MessageV2.FilePart.omit({ messageID: true, sessionID: true }),
      // Agent引用（如 @general）
      MessageV2.AgentPart.omit({ messageID: true, sessionID: true }),
      // 子任务
      MessageV2.SubtaskPart.omit({ messageID: true, sessionID: true }),
    ])
  ),
})
```

**大白话解释**：
- `sessionID` = 房间号（你在哪个聊天室说话）
- `parts` = 你说的话（可以是文字、文件、引用其他Agent等）
- `agent` = 指定哪个"工作人员"来处理（默认 build）
- `model` = 指定哪个"翻译官"来理解（默认用上次用的）

---

## 🔧 第二站：精密分拣车间（createUserMessage）

这是 Step 1 的**核心环节**，就像快递分拣中心的精密车间，把用户的输入拆解、包装、贴上标签。

### 整体流程

```typescript
// packages/opencode/src/session/prompt.ts 第 963 行开始

async function createUserMessage(input: PromptInput) {
  // 1️⃣ 确定使用哪个 Agent
  const agent = await Agent.get(input.agent ?? (await Agent.defaultAgent()))

  // 2️⃣ 确定使用哪个 AI 模型
  const model = input.model ?? agent.model ?? (await lastModel(input.sessionID))
  const full = !input.variant && agent.variant
    ? await Provider.getModel(model.providerID, model.modelID).catch(() => undefined)
    : undefined
  const variant = input.variant ?? (agent.variant && full?.variants?.[agent.variant] 
    ? agent.variant : undefined)

  // 3️⃣ 创建消息的"身份证"（元数据）
  const info: MessageV2.Info = {
    id: input.messageID ?? MessageID.ascending(),      // 唯一编号
    role: "user",                                       // 身份：用户发的
    sessionID: input.sessionID,                         // 所属会话
    time: { created: Date.now() },                      // 时间戳
    tools: input.tools,                                 // 工具配置
    agent: agent.name,                                  // 分配的Agent
    model,                                              // 使用的模型
    system: input.system,                               // 系统提示词覆盖
    format: input.format,                               // 输出格式要求
    variant,                                            // 模型变体
  }
  
  // 4️⃣ 设置清理钩子（函数结束时自动清理临时指令）
  using _ = defer(() => InstructionPrompt.clear(info.id))

  // 5️⃣ 处理内容块（核心中的核心！）
  const parts = await Promise.all(
    input.parts.map(async (part): Promise<Draft<MessageV2.Part>[]> => {
      // 根据不同类型的内容，进行不同处理...
      // 后面详细讲
    })
  )

  // 6️⃣ 保存到数据库
  const flat = parts.flat()
  await MessageV2.insert(info, flat)

  // 7️⃣ 发送"新消息到达"事件（通知UI更新）
  Bus.emit(BusEvent.MessageAdded, { 
    messageID: info.id, 
    sessionID: input.sessionID 
  })

  // 8️⃣ 返回完整的消息对象
  return { ...info, parts: flat }
}
```

---

## 🏷️ 子步骤详解

### 1️⃣ 确认"快递员"身份（选择 Agent）

```typescript
const agent = await Agent.get(input.agent ?? (await Agent.defaultAgent()))
```

**大白话**：系统问"用户指定了哪个快递员？没指定就用默认的（build）"

Agent 就像不同类型的快递员：
- **build** → 全能快递员（默认，啥都能干）
- **plan** → 只看不摸的观察员（只读模式）
- **general** → 专门跑腿的小弟（子Agent）

### 2️⃣ 确认"翻译官"（选择模型）

```typescript
const model = input.model ?? agent.model ?? (await lastModel(input.sessionID))
```

这是选择用哪个 AI 模型来处理：
- Claude？GPT？Gemini？
- 优先级：用户指定 > Agent偏好 > 上次用的

**代码解析**：
- `input.model` = 用户这次指定的模型
- `agent.model` = 这个Agent偏好的模型
- `lastModel()` = 获取这个会话上次用的模型

### 3️⃣ 制作"身份档案"（创建 Info 对象）

```typescript
const info: MessageV2.Info = {
  id: input.messageID ?? MessageID.ascending(),      // 🏷️ 快递单号（唯一ID）
  role: "user",                                       // 🏷️ 发件人：用户
  sessionID: input.sessionID,                         // 🏷️ 目的地（哪个会话）
  time: { created: Date.now() },                      // 🏷️ 发货时间
  tools: input.tools,                                 // 🏷️ 特殊工具配置
  agent: agent.name,                                  // 🏷️ 分配快递员
  model,                                              // 🏷️ 指定翻译官
  system: input.system,                               // 🏷️ 特殊系统提示词
  format: input.format,                               // 🏷️ 期望回复格式
  variant,                                            // 🏷️ 模型变体
}
```

这就像给快递包裹贴上**完整的物流标签**，记录所有关键信息。

---

## 🧩 核心：内容拆解包装（处理 Parts）

用户的输入可能不只是文字，还可能包含文件、引用其他Agent、子任务等。

```
用户发送的内容 ───────────────────────────────────►
                                                      │
        ┌──────────────────┬──────────────────┬──────┴──────┐
        ▼                  ▼                  ▼             ▼
   ┌─────────┐      ┌─────────┐       ┌─────────┐   ┌──────────┐
   │  文字   │      │  文件   │       │ MCP资源 │   │ 子任务   │
   │  text   │      │  file   │       │ resource│   │ subtask  │
   └─────────┘      └─────────┘       └─────────┘   └──────────┘
        │                  │                  │            │
        ▼                  ▼                  ▼            ▼
   "帮我修bug"       src/sum.ts        外部API数据     @general
                     文件内容                         召唤子Agent
```

### 处理文字 Part（最简单的情况）

```typescript
// 如果 part.type === "text"
{
  type: "text",
  text: "我运行 bun test 报错了...",
  // 会被包装成：
  {
    id: "part_001",
    messageID: "msg_001",
    sessionID: "sess_abc",
    type: "text",
    text: "我运行 bun test 报错了..."
  }
}
```

### 处理文件 Part（拖拽文件或 @引用）

```typescript
// packages/opencode/src/session/prompt.ts 第 1092-1199 行

if (part.type === "file") {
  const url = new URL(part.url)
  
  switch (url.protocol) {
    case "file:":
      // 本地文件处理
      const filepath = fileURLToPath(part.url)
      const s = Filesystem.stat(filepath)
      
      if (s?.isDirectory()) {
        part.mime = "application/x-directory"
      }
      
      if (part.mime === "text/plain") {
        // 读取文件内容
        const pieces: Draft<MessageV2.Part>[] = [
          {
            messageID: info.id,
            sessionID: input.sessionID,
            type: "text",
            synthetic: true,  // 标记为"系统自动生成"
            text: `Called the Read tool with the following input: ${JSON.stringify(args)}`,
          },
        ]
        
        // 实际调用 ReadTool 读取文件
        await ReadTool.init().then(async (t) => {
          const result = await t.execute({ path: filepath })
          pieces.push({
            messageID: info.id,
            sessionID: input.sessionID,
            type: "text",
            synthetic: true,
            text: result.content,  // 文件的实际内容
          })
        })
        
        return pieces
      }
  }
}
```

**大白话**：如果用户拖进来一个文件（比如 `sum.ts`），系统会：
1. 生成一条系统消息："调用了 Read 工具读取了 sum.ts"
2. 实际读取文件内容
3. 把文件内容作为另一条消息附加

### 处理 MCP 资源 Part

```typescript
// packages/opencode/src/session/prompt.ts 第 998-1062 行

if (part.source?.type === "resource") {
  const { clientName, uri } = part.source
  log.info("mcp resource", { clientName, uri, mime: part.mime })

  const pieces: Draft<MessageV2.Part>[] = [
    {
      messageID: info.id,
      sessionID: input.sessionID,
      type: "text",
      synthetic: true,
      text: `Reading MCP resource: ${part.filename} (${uri})`,
    },
  ]

  try {
    // 调用 MCP 客户端读取外部资源
    const resourceContent = await MCP.readResource(clientName, uri)
    
    // 处理返回的内容
    const contents = Array.isArray(resourceContent.contents)
      ? resourceContent.contents
      : [resourceContent.contents]

    for (const content of contents) {
      if ("text" in content && content.text) {
        pieces.push({
          messageID: info.id,
          sessionID: input.sessionID,
          type: "text",
          synthetic: true,
          text: content.text,
        })
      }
    }
    
    return pieces
  } catch (error) {
    // 错误处理...
  }
}
```

**大白话**：MCP 资源就像是引用外部系统的数据（比如数据库、API），系统会调用对应的 MCP 客户端去拉取数据。

---

## 📦 最终产物：MessageV2 对象

经过 Step 1 的处理，用户的输入被转换成了这样的结构：

```typescript
// packages/opencode/src/session/message-v2.ts

{
  // ========== 基本信息（Info）==========
  id: "msg_001",                       // 消息唯一ID
  role: "user",                        // 角色：user/assistant
  sessionID: "sess_abc",               // 所属会话
  
  time: {                              // 时间信息
    created: 1710739200000,            // 创建时间戳
    completed: undefined               // 完成时间（用户消息没有）
  },
  
  // ========== 处理配置 ==========
  agent: "build",                      // 分配给哪个Agent处理
  model: {                             // 使用的AI模型
    providerID: "anthropic",
    modelID: "claude-3-5-sonnet-20241022"
  },
  
  // ========== 内容块（Parts）==========
  parts: [
    {
      id: "part_001",
      type: "text",
      text: "我运行 bun test 报错了...",  // 用户原话
      messageID: "msg_001",
      sessionID: "sess_abc"
    },
    {
      id: "part_002",
      type: "text",
      text: "Called the Read tool...",     // 系统自动生成的上下文
      synthetic: true,
      messageID: "msg_001",
      sessionID: "sess_abc"
    }
  ],
  
  // ========== 工具执行记录（后续填充）==========
  tools: {},
  
  // ========== 元数据（Assistant回复时填充）==========
  metadata: {
    assistant: { ... },                 // AI模型相关信息
    tokens: {                           // Token消耗统计
      input: 150,
      output: 320,
      reasoning: 50,
      cache: { read: 0, write: 0 }
    }
  }
}
```

---

## 🎯 形象比喻总结

| 现实场景 | OpenCode Step 1 |
|---------|----------------|
| 快递到达分拣中心 | 用户输入到达 `prompt()` 函数 |
| 查看寄件信息 | 解析 `PromptInput` 对象 |
| 确认快递员身份 | 选择 Agent（build/plan/...） |
| 指派翻译官 | 选择 AI 模型 |
| 给包裹贴标签 | 创建 `MessageV2.Info` |
| 拆解包装 | 处理不同类型的 `parts` |
| 录入物流系统 | `MessageV2.insert()` 存入数据库 |
| 广播通知 | `Bus.emit()` 发送事件 |
| 送往下一站 | 进入 `loop()` 主循环 |

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| 入口函数 | `packages/opencode/src/session/prompt.ts` | 160-187 |
| PromptInput 定义 | `packages/opencode/src/session/prompt.ts` | 93-158 |
| 创建用户消息 | `packages/opencode/src/session/prompt.ts` | 963+ |
| 处理文字Part | `packages/opencode/src/session/prompt.ts` | 1062-1092 |
| 处理文件Part | `packages/opencode/src/session/prompt.ts` | 1092-1199 |
| 处理MCP资源 | `packages/opencode/src/session/prompt.ts` | 998-1062 |
| MessageV2 数据结构 | `packages/opencode/src/session/message-v2.ts` | 1-200 |
| 消息Schema定义 | `packages/opencode/src/session/message.ts` | 1-191 |

---

## 🚀 下一步

完成 Step 1 后，系统会：
1. 把消息存入数据库
2. 发送事件通知 UI 更新
3. 进入 `Step 2: 确定使用哪个 Agent`

实际上在 `createUserMessage` 中已经确定了 Agent，但那是**数据层面**的绑定。下一步是**逻辑层面**的确认——检查这个 Agent 的配置、权限等。

准备好进入 **Step 2** 了吗？
