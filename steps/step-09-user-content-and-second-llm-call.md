# Step 9: User Content 组装和第二次 LLM 调用

## 概览

在工具执行完成后，OpenCode 需要将工具结果组装成模型可理解的消息格式，然后进行第二次 LLM 调用，让 AI 基于工具执行结果生成最终回复。

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Step 9: 结果处理与回复生成                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   Tool 执行完成                                                                  │
│        │                                                                        │
│        ▼                                                                        │
│   ┌──────────────────────┐                                                     │
│   │ 1. Tool Result 保存   │  更新 Part 状态为 completed/error                  │
│   └──────────────────────┘                                                     │
│        │                                                                        │
│        ▼                                                                        │
│   ┌──────────────────────┐                                                     │
│   │ 2. 消息格式转换       │  MessageV2.toModelMessages()                       │
│   │                      │  - 内部格式 → UI 格式 → Model 格式                  │
│   └──────────────────────┘                                                     │
│        │                                                                        │
│        ▼                                                                        │
│   ┌──────────────────────┐                                                     │
│   │ 3. 第二次 LLM 调用    │  streamText()                                      │
│   │                      │  - 包含 tool results                                 │
│   │                      │  - AI 生成基于结果的回复                             │
│   └──────────────────────┘                                                     │
│        │                                                                        │
│        ▼                                                                        │
│   ┌──────────────────────┐                                                     │
│   │ 4. 循环结束或继续     │  - AI 回复完成 → 退出循环                          │
│   │                      │  - AI 调用更多工具 → 继续循环                       │
│   └──────────────────────┘                                                     │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Tool Result 保存

工具执行完成后，结果会被保存到数据库中：

```typescript
// packages/opencode/src/session/prompt.ts 第 469-485 行

if (result && part.state.status === "running") {
  await Session.updatePart({
    ...part,
    state: {
      status: "completed",           // 状态更新为完成
      input: part.state.input,       // 工具输入参数
      title: result.title,           // 工具执行标题
      metadata: result.metadata,     // 元数据（进度信息等）
      output: result.output,         // 工具输出内容
      attachments,                   // 附件（图片、文件等）
      time: {
        ...part.state.time,
        end: Date.now(),             // 记录结束时间
      },
    },
  })
}
```

### 错误处理

如果工具执行失败：

```typescript
// packages/opencode/src/session/prompt.ts 第 487-500 行

if (!result) {
  await Session.updatePart({
    ...part,
    state: {
      status: "error",               // 状态更新为错误
      error: executionError ? `Tool execution failed: ${executionError.message}` 
                           : "Tool execution failed",
      time: {
        start: part.state.status === "running" ? part.state.time.start : Date.now(),
        end: Date.now(),
      },
      input: part.state.input,
    },
  })
}
```

---

## 2. 消息格式转换

### 2.1 三层消息格式

OpenCode 使用三种消息表示：

| 层级 | 类型 | 用途 |
|------|------|------|
| **Internal** | `MessageV2.WithParts` | 数据库存储格式 |
| **UI** | `UIMessage` | 界面展示格式 |
| **Model** | `ModelMessage` | LLM API 格式 |

### 2.2 转换流程

```typescript
// packages/opencode/src/session/message-v2.ts 第 497-730 行

export function toModelMessages(
  input: WithParts[],      // 内部格式消息
  model: Provider.Model,   // 模型配置
  options?: { stripMedia?: boolean }
): ModelMessage[] {
  
  // Step 1: Internal → UI
  const uiMessages: UIMessage[] = []
  
  for (const msg of input) {
    if (msg.info.role === "user") {
      // 转换用户消息...
    }
    
    if (msg.info.role === "assistant") {
      // 转换助手消息...
      for (const part of msg.parts) {
        if (part.type === "tool") {
          // 转换 tool result
          if (part.state.status === "completed") {
            assistantMessage.parts.push({
              type: ("tool-" + part.tool) as `tool-${string}`,
              state: "output-available",
              toolCallId: part.callID,
              input: part.state.input,
              output: {
                text: outputText,
                attachments: finalAttachments,
              },
            })
          }
          
          if (part.state.status === "error") {
            assistantMessage.parts.push({
              type: ("tool-" + part.tool) as `tool-${string}`,
              state: "output-error",
              toolCallId: part.callID,
              input: part.state.input,
              errorText: part.state.error,
            })
          }
        }
      }
    }
  }
  
  // Step 2: UI → Model (通过 ai SDK 的 convertToModelMessages)
  return convertToModelMessages(uiMessages, { tools })
}
```

### 2.3 Tool Result 的特殊处理

#### 媒体文件处理

某些 Provider（如 OpenAI）不支持在 tool result 中直接包含图片/PDF，需要特殊处理：

```typescript
// packages/opencode/src/session/message-v2.ts 第 513-523 行

const supportsMediaInToolResults = (() => {
  if (model.api.npm === "@ai-sdk/anthropic") return true
  if (model.api.npm === "@ai-sdk/openai") return true
  if (model.api.npm === "@ai-sdk/amazon-bedrock") return true
  if (model.api.npm === "@ai-sdk/google-vertex/anthropic") return true
  if (model.api.npm === "@ai-sdk/google") {
    const id = model.api.id.toLowerCase()
    return id.includes("gemini-3") && !id.includes("gemini-2")
  }
  return false
})()

// 如果不支持，将媒体文件提取为单独的 user message
if (!supportsMediaInToolResults && mediaAttachments.length > 0) {
  result.push({
    id: MessageID.ascending(),
    role: "user",
    parts: [
      { type: "text", text: "Attached image(s) from tool result:" },
      ...media.map((attachment) => ({
        type: "file",
        url: attachment.url,
        mediaType: attachment.mime,
      })),
    ],
  })
}
```

#### Compaction 标记处理

被 compaction 清理的旧 tool result：

```typescript
// packages/opencode/src/session/message-v2.ts 第 638 行

const outputText = part.state.time.compacted 
  ? "[Old tool result content cleared]"  // 被清理的内容显示占位符
  : part.state.output                     // 正常内容
```

### 2.4 最终的消息结构

```json
{
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "读取 README.md" },
    { 
      "role": "assistant", 
      "content": null,
      "tool_calls": [
        {
          "id": "call_xxx",
          "type": "function",
          "function": {
            "name": "read",
            "arguments": "{\"filePath\": \"README.md\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_xxx",
      "content": "# OpenCode\n\nOpenCode is an AI coding agent..."
    }
  ]
}
```

---

## 3. 第二次 LLM 调用

### 3.1 调用位置

```typescript
// packages/opencode/src/session/prompt.ts 第 665-685 行

const result = await processor.process({
  user: lastUser,
  agent,
  abort,
  sessionID,
  system,                                    // System Prompt
  messages: [
    ...MessageV2.toModelMessages(msgs, model),  // 转换后的消息历史
    ...(isLastStep ? [{ role: "assistant", content: MAX_STEPS }] : []),
  ],
  tools,                                     // 可用工具列表
  model,
  toolChoice: format.type === "json_schema" ? "required" : undefined,
})
```

### 3.2 与第一次调用的区别

| 方面 | 第一次调用 | 第二次调用 |
|------|-----------|-----------|
| **触发时机** | 用户输入后 | Tool 执行完成后 |
| **消息内容** | 用户原始输入 | 用户输入 + Tool Results |
| **AI 行为** | 分析需求，选择工具 | 基于结果生成回复 |
| **预期输出** | Tool Calls | 文本回复或更多 Tool Calls |

### 3.3 可能的 AI 响应

#### 场景 A：直接回复（完成）

```
AI: "根据 README.md 的内容，这是一个 AI 编码助手项目，主要功能包括..."

结果：finish = "stop"，退出循环
```

#### 场景 B：调用更多工具（继续）

```
AI: 调用 read({ filePath: "package.json" })

结果：finish = "tool-calls"，继续循环，执行工具
```

#### 场景 C：结构化输出模式

```typescript
// packages/opencode/src/session/prompt.ts 第 689-708 行

// 如果配置了 JSON Schema 输出格式
if (lastUser.format?.type === "json_schema") {
  // 注入 StructuredOutput 工具
  tools["StructuredOutput"] = createStructuredOutputTool({
    schema: lastUser.format.schema,
    onSuccess(output) {
      structuredOutput = output
    },
  })
}

// AI 必须调用 StructuredOutput 工具
if (structuredOutput !== undefined) {
  processor.message.structured = structuredOutput
  processor.message.finish = "stop"
  await Session.updateMessage(processor.message)
  break  // 退出循环
}

// 如果 AI 没有调用 StructuredOutput 工具
if (modelFinished && format.type === "json_schema") {
  processor.message.error = new MessageV2.StructuredOutputError({
    message: "Model did not produce structured output",
    retries: 0,
  }).toObject()
  break
}
```

---

## 4. 循环控制与结束

### 4.1 循环继续的条件

```typescript
// packages/opencode/src/session/prompt.ts 第 711-721 行

if (result === "stop") break  // 正常结束

if (result === "compact") {
  // 需要 compaction，创建 compaction 任务后继续
  await SessionCompaction.create({
    sessionID,
    agent: lastUser.agent,
    model: lastUser.model,
    auto: true,
    overflow: !processor.message.finish,
  })
}
continue  // 继续循环
```

### 4.2 结束后的清理

```typescript
// packages/opencode/src/session/prompt.ts 第 723-732 行

SessionCompaction.prune({ sessionID })  // 轻量清理

// 通知等待的回调
for await (const item of MessageV2.stream(sessionID)) {
  if (item.info.role === "user") continue
  const queued = state()[sessionID]?.callbacks ?? []
  for (const q of queued) {
    q.resolve(item)  // 返回最终消息
  }
  return item
}
```

---

## 5. 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Step 9 完整流程                                      │
└─────────────────────────────────────────────────────────────────────────────┘

  Tool 执行完成
       │
       ▼
  ┌─────────────────────────────────────┐
  │ 保存 Tool Result 到数据库            │
  │ - status: "completed"/"error"       │
  │ - output: 工具输出内容               │
  │ - attachments: 附件列表              │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │ 消息格式转换 (toModelMessages)       │
  │                                     │
  │ Internal (WithParts)                │
  │      │                              │
  │      ▼                              │
  │    UI (UIMessage)                   │
  │      │                              │
  │      ▼                              │
  │   Model (ModelMessage)              │
  │      │                              │
  │      └── 特殊处理：                  │
  │          - 媒体文件提取              │
  │          - Compaction 占位符         │
  │          - 错误状态标记              │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │ 组装第二次 LLM 调用参数              │
  │ - system: System Prompt             │
  │ - messages: 完整消息历史             │
  │ - tools: 可用工具列表                │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │ 第二次 LLM 调用 (streamText)         │
  │                                     │
  │ AI 看到：用户问题 + Tool Results     │
  └─────────────────────────────────────┘
       │
       ├── AI 直接回复 ─────────────────┐
       │                                 ▼
       │                          ┌─────────────┐
       │                          │ finish=stop │
       │                          └──────┬──────┘
       │                                 │
       ▼                                 ▼
  ┌─────────────────┐           ┌──────────────┐
  │ AI 调用更多工具 │           │ 循环结束     │
  │                 │           │              │
  │ finish=tool-    │           │ 返回最终消息 │
  │ calls           │           │ 给调用方     │
  └────────┬────────┘           └──────────────┘
           │
           ▼
    回到 Step 8 (Tool 执行)
```

---

## 6. 关键设计要点

### 6.1 为什么需要第二次 LLM 调用？

| 设计 | 说明 |
|------|------|
| **分离关注点** | 第一次调用决定"做什么"，第二次调用决定"说什么" |
| **Tool Results 上下文** | AI 需要看到 tool results 才能给出准确回复 |
| **迭代处理** | 支持多轮工具调用直到任务完成 |

### 6.2 消息格式的兼容性

```
不同 Provider 的差异处理：
├── Anthropic: 支持 tool result 中的图片
├── OpenAI: 支持 tool result 中的图片  
├── Google: 部分支持（仅 Gemini-3）
└── 其他: 需要将媒体提取为单独的 user message
```

### 6.3 Compaction 对消息的影响

```
被 Compaction 的 Tool Result：
- 原始内容被替换为 "[Old tool result content cleared]"
- 保留 tool 调用记录（用于对话连贯性）
- 节省上下文空间
```

---

## 7. 相关代码文件

| 文件 | 作用 |
|------|------|
| `packages/opencode/src/session/prompt.ts` | 主循环，第二次 LLM 调用 |
| `packages/opencode/src/session/message-v2.ts` | 消息格式转换 `toModelMessages()` |
| `packages/opencode/src/session/processor.ts` | `SessionProcessor.process()` 封装 LLM 调用 |

---

## 8. 总结

Step 9 的核心任务：

1. **保存结果**：将 tool execution 结果持久化到数据库
2. **格式转换**：将内部消息格式转换为 LLM API 格式
3. **第二次调用**：让 AI 基于 tool results 生成回复
4. **循环控制**：决定是结束对话还是继续执行更多工具

这是 OpenCode 对话流程的最后一个关键步骤，完成了从"执行"到"回复"的闭环。
