# Step 7: 第一次调用 LLM —— 真正的"对话开始"

> **一句话总结**：把准备好的 System Prompt、消息历史和工具列表发送给 LLM，开始流式对话，并实时处理 AI 的回复和工具调用。

---

## 🎬 场景回顾

前六步完成了：
1. ✅ **Step 1**：用户消息已打包
2. ✅ **Step 2**：确定使用 build Agent
3. ✅ **Step 3**：Agent 配置绑定到会话
4. ✅ **Step 4**：检查并压缩会话状态
5. ✅ **Step 5**：组装 System Prompt
6. ✅ **Step 6**：组装可用工具列表

现在万事俱备，**真正的对话要开始了**！系统会把所有准备好的内容发送给 LLM。

---

## 📡 消息组装与发送

### 完整的消息结构

```
发送给 LLM 的消息列表
│
├── System Message (系统提示词)
│   └── "You are OpenCode, the best coding agent..."
│       + 环境信息
│       + 项目指令 (AGENTS.md)
│       + 技能介绍
│
├── Message 1: User (历史消息)
│   └── "帮我修复 bun test 报错..."
│
├── Message 2: Assistant (历史回复)
│   ├── Text: "我来帮你看看..."
│   └── Tool: bash("bun test")
│
├── Message 3: User (工具结果)
│   └── Tool Result: 错误堆栈...
│
├── Message 4: Assistant (历史回复)
│   └── Text: "找到了问题..."
│
└── Message N: User (最新消息)
    └── "继续修复..."
```

### 代码实现

```typescript
// packages/opencode/src/session/prompt.ts 第 665-685 行

const result = await processor.process({
  user: lastUser,                    // 最后一个用户消息
  agent,                             // Agent 配置
  abort,                             // 取消信号
  sessionID,
  system,                            // ⭐ System Prompt
  messages: [
    ...MessageV2.toModelMessages(msgs, model),  // ⭐ 历史消息
    ...(isLastStep ? [{ role: "assistant", content: MAX_STEPS }] : []),
  ],
  tools,                             // ⭐ 可用工具
  model,
  toolChoice: format.type === "json_schema" ? "required" : undefined,
})
```

---

## 🔄 流式处理架构

OpenCode 使用 **Vercel AI SDK** 的 `streamText` 进行流式对话：

```
┌─────────────────────────────────────────────────────────────────┐
│                         流式处理流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Request                                                    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────┐                                            │
│  │  LLM.stream()   │  调用 AI SDK                               │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  for await...   │  逐块接收响应                              │
│  │  of stream.     │                                            │
│  │  fullStream     │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│     ┌─────┴─────┬─────────┬─────────┬─────────┐                 │
│     ▼           ▼         ▼         ▼         ▼                 │
│  text-      tool-     reason-   step-    finish               │
│  delta      call      ing       start    -step                │
│     │           │         │         │         │                 │
│     ▼           ▼         ▼         ▼         ▼                 │
│  实时显示    执行工具   显示思考   创建快照   计算用量         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 SessionProcessor 处理流

```typescript
// packages/opencode/src/session/processor.ts 第 46-349 行

export function create(input: {
  assistantMessage: MessageV2.Assistant
  sessionID: SessionID
  model: Provider.Model
  abort: AbortSignal
}) {
  const toolcalls: Record<string, MessageV2.ToolPart> = {}
  
  return {
    async process(streamInput: LLM.StreamInput) {
      const stream = await LLM.stream(streamInput)  // ⭐ 调用 LLM

      for await (const value of stream.fullStream) {  // ⭐ 处理流
        switch (value.type) {
          // 处理不同类型的事件...
        }
      }
    }
  }
}
```

### 事件类型处理

```typescript
for await (const value of stream.fullStream) {
  switch (value.type) {
    // 1️⃣ 开始生成文本
    case "text-start":
      currentText = { type: "text", text: "", ... }
      await Session.updatePart(currentText)
      break

    // 2️⃣ 文本增量更新
    case "text-delta":
      currentText.text += value.text
      await Session.updatePartDelta({...})
      break

    // 3️⃣ 文本结束
    case "text-end":
      currentText.text = currentText.text.trimEnd()
      await Session.updatePart(currentText)
      break

    // 4️⃣ 工具调用开始
    case "tool-call":
      await handleToolCall(value)
      break

    // 5️⃣ 工具执行结果
    case "tool-result":
      await handleToolResult(value)
      break

    // 6️⃣ 推理开始 (Reasoning)
    case "reasoning-start":
      // 创建 reasoning part
      break

    // 7️⃣ Step 开始
    case "start-step":
      snapshot = await Snapshot.track()  // 记录文件快照
      break

    // 8️⃣ Step 结束
    case "finish-step":
      // 计算 token 使用、生成 patch
      break
  }
}
```

---

## 🛠️ 工具调用处理

### 1. 工具调用开始

```typescript
case "tool-call": {
  const part = await Session.updatePart({
    id: PartID.ascending(),
    messageID: input.assistantMessage.id,
    sessionID: input.assistantMessage.sessionID,
    type: "tool",
    tool: value.toolName,           // 工具名称
    callID: value.id,               // 调用 ID
    state: {
      status: "running",
      input: value.input,           // 工具参数
      time: { start: Date.now() },
    },
  })
  toolcalls[value.toolCallId] = part as MessageV2.ToolPart

  // ⭐ Doom Loop 检测
  const parts = await MessageV2.parts(input.assistantMessage.id)
  const lastThree = parts.slice(-3)
  
  if (
    lastThree.length === 3 &&
    lastThree.every(p => 
      p.type === "tool" &&
      p.tool === value.toolName &&
      JSON.stringify(p.state.input) === JSON.stringify(value.input)
    )
  ) {
    // 检测到死循环！询问用户
    await PermissionNext.ask({
      permission: "doom_loop",
      patterns: [value.toolName],
      // ...
    })
  }
  break
}
```

**Doom Loop（死循环）是什么？**

```
场景：AI 陷入重复调用同一个工具的循环

Step 1: AI 调用 bash("ls src/")
Step 2: AI 调用 bash("ls src/")  // 重复！
Step 3: AI 调用 bash("ls src/")  // 再重复！

检测：连续 3 次调用相同的工具，参数相同
处理：询问用户是否继续
```

### 2. 工具执行结果

```typescript
case "tool-result": {
  const match = toolcalls[value.toolCallId]
  if (match) {
    await Session.updatePart({
      ...match,
      state: {
        status: "completed",
        input: value.input ?? match.state.input,
        output: value.output.output,     // 工具输出
        metadata: value.output.metadata,
        title: value.output.title,
        time: {
          start: match.state.time.start,
          end: Date.now(),
        },
      },
    })
    delete toolcalls[value.toolCallId]
  }
  break
}
```

### 3. 工具执行错误

```typescript
case "tool-error": {
  const match = toolcalls[value.toolCallId]
  if (match) {
    await Session.updatePart({
      ...match,
      state: {
        status: "error",
        error: (value.error as any).toString(),
        time: { start: match.state.time.start, end: Date.now() },
      },
    })

    // 如果是权限被拒绝，可能需要停止
    if (
      value.error instanceof PermissionNext.RejectedError ||
      value.error instanceof Question.RejectedError
    ) {
      blocked = shouldBreak
    }
    delete toolcalls[value.toolCallId]
  }
  break
}
```

---

## 🧠 Reasoning（推理过程）

某些模型（如 o1、o3、Claude 3.7）会展示推理过程：

```typescript
case "reasoning-start":
  const reasoningPart = {
    id: PartID.ascending(),
    type: "reasoning",
    text: "",
    time: { start: Date.now() },
    metadata: value.providerMetadata,
  }
  reasoningMap[value.id] = reasoningPart
  await Session.updatePart(reasoningPart)
  break

case "reasoning-delta":
  if (value.id in reasoningMap) {
    const part = reasoningMap[value.id]
    part.text += value.text  // 累加推理内容
    await Session.updatePartDelta({
      sessionID: part.sessionID,
      messageID: part.messageID,
      partID: part.id,
      field: "text",
      delta: value.text,
    })
  }
  break

case "reasoning-end":
  if (value.id in reasoningMap) {
    const part = reasoningMap[value.id]
    part.text = part.text.trimEnd()
    part.time = { ...part.time, end: Date.now() }
    await Session.updatePart(part)
    delete reasoningMap[value.id]
  }
  break
```

**显示效果**：
```
User: 帮我优化这个算法

Assistant: 
[思考中...]
让我分析一下这个算法的时间复杂度。首先，我看到有一个嵌套循环...
[/思考中...]

根据分析，我建议使用哈希表来优化查找过程...
```

---

## 📊 Step 生命周期

每个 AI 的"思考-行动"周期称为一个 Step：

```
Step Start (start-step)
    │
    ├── 创建文件快照 (Snapshot.track)
    │
    ├── AI 生成回复
    │   ├── 文本输出 (text-delta)
    │   └── 工具调用 (tool-call)
    │
    └── 工具执行
        ├── 成功 (tool-result)
        └── 失败 (tool-error)
    │
Step Finish (finish-step)
    │
    ├── 计算 Token 使用
    ├── 计算成本
    ├── 生成文件 Patch
    └── 保存 Assistant 消息
```

### Step Finish 处理

```typescript
case "finish-step":
  // 1. 计算 token 使用和成本
  const usage = Session.getUsage({
    model: input.model,
    usage: value.usage,
    metadata: value.providerMetadata,
  })
  
  input.assistantMessage.finish = value.finishReason
  input.assistantMessage.cost += usage.cost
  input.assistantMessage.tokens = usage.tokens
  
  // 2. 创建 step-finish part
  await Session.updatePart({
    type: "step-finish",
    reason: value.finishReason,
    snapshot: await Snapshot.track(),
    tokens: usage.tokens,
    cost: usage.cost,
  })

  // 3. 生成文件变更 Patch
  if (snapshot) {
    const patch = await Snapshot.patch(snapshot)
    if (patch.files.length) {
      await Session.updatePart({
        type: "patch",
        hash: patch.hash,
        files: patch.files,
      })
    }
  }

  // 4. 触发会话摘要生成
  SessionSummary.summarize({
    sessionID: input.sessionID,
    messageID: input.assistantMessage.parentID,
  })

  // 5. 检查是否需要压缩
  if (await SessionCompaction.isOverflow({ tokens: usage.tokens, model: input.model })) {
    needsCompaction = true
  }
  break
```

---

## 🎯 形象比喻：医生问诊

| 现实场景 | OpenCode Step 7 |
|---------|----------------|
| 医生查看病历 | 组装 System Prompt + 历史消息 |
| 病人描述症状 | 用户最新消息 |
| 医生开始诊断 | LLM.stream() 调用 |
| 医生边想边说 | text-delta 流式输出 |
| 医生内心思考 | reasoning 事件 |
| 医生开检查单 | tool-call 事件 |
| 护士执行检查 | 工具 execute |
| 检查结果返回 | tool-result 事件 |
| 医生记录病历 | updatePart 保存 |
| 一轮问诊结束 | finish-step |

**完整场景**：

> 医生（LLM）正在看诊：
> 
> 1. **查看病历**（System Prompt + History）：了解病人基本情况、过往病史
> 2. **病人描述**（User Message）："我最近总是头晕..."
> 3. **医生思考**（Reasoning）："头晕可能有很多原因...血压？贫血？"
> 4. **医生询问**（Text Delta）："请问你最近睡眠如何？"
> 5. **医生开检查**（Tool Call）："我先给你开个血压检查"
> 6. **护士执行**（Tool Execute）：测量血压
> 7. **结果返回**（Tool Result）："血压 140/90，偏高"
> 8. **医生诊断**（Text Delta）："你的血压偏高，可能是这个原因..."
> 9. **记录病历**（Update Part）：保存这一轮问诊记录
> 10. **问诊结束**（Finish Step）：准备下一轮

---

## 🔄 主循环中的位置

```
while (true) {  // 主循环
  Step 4: 检查是否需要压缩
    │
    ▼
  Step 5: 组装 System Prompt
    │
    ▼
  Step 6: 组装工具列表
    │
    ▼
  Step 7: 调用 LLM  ⭐ 你在这里
    │
    ├── processor.process()
    │     ├── LLM.stream()      开始流式调用
    │     ├── for await...      处理流式事件
    │     │     ├── text-delta  文本输出
    │     │     ├── tool-call   工具调用
    │     │     ├── tool-result 工具结果
    │     │     └── finish-step Step 结束
    │     └── return result     返回处理结果
    │
    ▼
  检查 result
    │
    ├── "stop" → 退出循环
    └── "continue" → 继续下一轮
}
```

---

## 💡 关键设计思想

### 1. 流式处理的好处
- **实时反馈**：用户不用等待 AI 全部生成完
- **早期干预**：发现问题可以及时取消
- **自然体验**：类似人类打字的速度感

### 2. 事件驱动架构
- 每种事件类型独立处理
- 易于扩展新的事件类型
- 清晰的状态管理

### 3. Doom Loop 防护
- 自动检测重复工具调用
- 防止 AI "钻牛角尖"
- 保护用户 token 不被浪费

### 4. 快照与 Patch
- Step 开始时记录文件状态
- Step 结束时计算变更
- 支持撤销和回顾

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| 调用 LLM | `packages/opencode/src/session/llm.ts` | 46-200 |
| 流式处理 | `packages/opencode/src/session/processor.ts` | 46-349 |
| 消息组装 | `packages/opencode/src/session/prompt.ts` | 665-685 |
| 历史消息转换 | `packages/opencode/src/session/message-v2.ts` | - |
| Doom Loop 检测 | `packages/opencode/src/session/processor.ts` | 152-177 |
| 工具执行 | `packages/opencode/src/tool/tool.ts` | - |

---

## 🚀 下一步

完成 Step 7 后：
1. ✅ LLM 生成了回复
2. ✅ 可能调用了工具
3. ✅ 工具执行完成
4. ✅ 结果返回给 LLM

接下来进入 **Step 8: 执行工具调用（bash）**——当 AI 决定运行命令时会发生什么。

准备好进入 **Step 8** 了吗？
