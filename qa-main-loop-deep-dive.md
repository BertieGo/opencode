# 深度解析：主循环的停止条件与迭代机制

## 问题 1：决定停止主循环的底层原理是什么？

### 核心决策点

```
┌─────────────────────────────────────────────────────────────────────┐
│                    主循环停止的 5 个条件                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 🏁 LLM 主动完成（最常见）                                        │
│     └─ finishReason = "stop" | "end_turn" | "content_filter"        │
│     └─ AI 没有调用任何工具，直接生成完整回复                            │
│                                                                     │
│  2. 🚫 权限被拒绝（blocked = true）                                  │
│     └─ 用户拒绝了权限请求（如 bash、edit）                            │
│     └─ 且 experimental.continue_loop_on_deny !== true               │
│                                                                     │
│  3. 💥 发生不可恢复错误（error）                                      │
│     └─ LLM 调用失败（API 错误、网络问题）                             │
│     └─ 工具执行错误且无法恢复                                         │
│                                                                     │
│  4. ✅ 结构化输出完成                                                 │
│     └─ 配置了 JSON Schema 输出                                       │
│     └─ AI 成功调用 StructuredOutput 工具                             │
│                                                                     │
│  5. 📋 结构化输出失败                                                 │
│     └─ 配置了 JSON Schema 输出                                       │
│     └─ AI 没有调用 StructuredOutput 工具就停止了                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 代码层面的决策链

```typescript
// packages/opencode/src/session/processor.ts

class SessionProcessor {
  let blocked = false      // 权限阻止标志
  let needsCompaction = false  // 需要压缩标志

  async process() {
    // 1. 调用 LLM
    const stream = await LLM.stream({...})
    
    for await (const event of stream) {
      switch (event.type) {
        case "finish-step":
          // 记录 finishReason
          assistantMessage.finish = event.finishReason  // "stop" | "tool-calls" | ...
          
        case "tool-error":
          if (event.error instanceof PermissionNext.RejectedError) {
            blocked = shouldBreak  // 🚫 标记为阻止
          }
      }
    }

    // 2. 返回结果给主循环
    if (needsCompaction) return "compact"
    if (blocked) return "stop"           // 🚫 权限阻止 → 停止
    if (assistantMessage.error) return "stop"  // 💥 错误 → 停止
    return "continue"                    // 🔄 继续下一轮
  }
}
```

```typescript
// packages/opencode/src/session/prompt.ts (主循环)

while (true) {
  const result = await processor.process({...})

  // 3. 主循环的停止判断
  if (structuredOutput !== undefined) {
    break  // ✅ 结构化输出完成
  }

  const modelFinished = processor.message.finish && 
    !["tool-calls", "unknown"].includes(processor.message.finish)

  if (modelFinished && format.type === "json_schema" && !structuredOutput) {
    // 📋 结构化输出失败 → 停止（带错误）
    break
  }

  if (result === "stop") break  // 🚫💥 处理器要求停止
  if (result === "compact") {
    // 触发 compaction 后继续
    await SessionCompaction.create({...})
  }
  continue  // 🔄 继续下一轮
}
```

### finishReason 详解

| finishReason | 含义 | 处理方式 |
|-------------|------|----------|
| `"stop"` | AI 自然完成 | 正常退出 |
| `"end_turn"` | AI 结束回合 | 正常退出 |
| `"tool-calls"` | AI 调用了工具 | 🔄 继续循环 |
| `"length"` | 达到长度限制 | 退出（可能需要提示）|
| `"content_filter"` | 内容被过滤 | 退出 |
| `"unknown"` | 未知原因 | 🔄 继续循环（保守策略）|

### 图示：停止决策流程

```
LLM 流式输出完成
    │
    ▼
获取 finishReason
    │
    ├── "tool-calls" ──────────────────────┐
    │                                       ▼
    │                              ┌──────────────────┐
    │                              │ 执行工具调用      │
    │                              │ 等待 tool-result  │
    │                              └────────┬─────────┘
    │                                       │
    ▼                                       ▼
其他 finishReason                   工具执行完成
    │                                       │
    ▼                                       ▼
检查 blocked/error                  检查权限/错误
    │                                       │
    ├── 有 error ────┐              ┌───────┴───────┐
    │                 ▼              ▼               ▼
    │            return "stop"   被拒绝?        正常完成
    │                 │              │               │
    ▼                 │              ▼               ▼
return "continue" ◀───┴────── blocked=true     return "continue"
                             return "stop"
    │
    ▼
主循环收到结果
    │
    ├── "stop" ───────────┐
    │                      ▼
    │                   break
    │                      │
    │                      ▼
    │              🎉 退出主循环
    │
    ├── "compact" ────────┐
    │                      ▼
    │              触发 Compaction
    │                      │
    └──────────────┐       │
                   ▼       ▼
               continue（下一轮）
```

---

## 问题 2：进入下一轮的过程是什么，Prompt 会发生什么变化？

### 迭代过程全景图

```
Round 1: 初始状态
─────────────────────────────────────────────────────────
Messages: []
System: [环境, Provider指令, Skills, AGENTS.md]
Tools: [read, edit, bash, ...]

AI: "让我读取文件..."
[调用 read]

↓

执行 read 工具
↓

Round 2: 工具结果已加入
─────────────────────────────────────────────────────────
Messages: [
  { role: "user", content: "帮我优化代码" },
  { role: "assistant", content: "让我读取文件...",
    tool_calls: [{ name: "read", ... }] },
  { role: "tool", content: "文件内容..." }  ⭐ 新增
]
System: [环境, Provider指令, Skills, AGENTS.md]  ← 基本不变
Tools: [read, edit, bash, ...]  ← 可能微调

AI: "明白了，需要这样修改..."
[调用 edit]

↓

执行 edit 工具
↓

Round 3: 编辑结果已加入
─────────────────────────────────────────────────────────
Messages: [
  { role: "user", content: "帮我优化代码" },
  { role: "assistant", content: "让我读取文件...", tool_calls: [...] },
  { role: "tool", content: "文件内容..." },
  { role: "assistant", content: "需要这样修改...", tool_calls: [...] },
  { role: "tool", content: "编辑成功" }  ⭐ 新增
]
System: [环境, Provider指令, Skills, AGENTS.md]
Tools: [read, edit, bash, ...]

AI: "让我测试一下..."
[调用 bash]

↓

执行 bash 工具
↓

Round 4: 测试结果已加入
─────────────────────────────────────────────────────────
Messages: [
  ...前面所有消息...,
  { role: "assistant", content: "让我测试...", tool_calls: [...] },
  { role: "tool", content: "测试通过 ✓" }  ⭐ 新增
]
System: [环境, Provider指令, Skills, AGENTS.md]
Tools: [read, edit, bash, ...]

AI: "优化完成！这是修改总结..."
[没有调用工具]

↓

finishReason = "stop"
↓

🎉 退出循环
```

### Prompt 的具体变化

#### System Prompt（基本不变）

```typescript
// 每一轮都会重新组装，但内容基本一致

const system = [
  ...(await SystemPrompt.environment(model)),   // 环境信息（时间会变）
  ...(skills ? [skills] : []),                   // Skills（基本不变）
  ...(await InstructionPrompt.system()),         // AGENTS.md（不变）
]

// 只有 environment 中的时间等动态信息会变化
```

#### Messages（每轮追加）

```typescript
// packages/opencode/src/session/message-v2.ts

// Round 1 发送给 LLM:
messages = [
  { role: "user", content: "帮我优化代码" }
]

// Round 2 发送给 LLM:
messages = [
  { role: "user", content: "帮我优化代码" },
  { 
    role: "assistant", 
    content: "让我读取文件...",
    tool_calls: [{ id: "call_1", function: { name: "read", arguments: "..." } }]
  },
  { 
    role: "tool", 
    tool_call_id: "call_1",
    content: "文件内容：export function sum(...)"  // ⭐ 工具结果
  }
]

// Round 3 发送给 LLM:
messages = [
  ...前面的所有消息...,
  {
    role: "assistant",
    content: "明白了，需要这样修改...",
    tool_calls: [{ id: "call_2", function: { name: "edit", arguments: "..." } }]
  },
  {
    role: "tool",
    tool_call_id: "call_2",
    content: "File updated successfully"  // ⭐ 新工具结果
  }
]

// 以此类推...
```

### 代码层面的迭代过程

```typescript
// packages/opencode/src/session/prompt.ts

while (true) {
  // 1. 获取当前所有消息（包括历史）
  const msgs = await MessageV2.list(sessionID)
  // msgs 每轮都会增长，因为追加了新的 assistant + tool 消息

  // 2. 组装 System Prompt（基本不变）
  const system = [
    ...(await SystemPrompt.environment(model)),
    ...(await SystemPrompt.skills(agent)),
    ...(await InstructionPrompt.system()),
  ]

  // 3. 获取工具列表（可能微调）
  const tools = await resolveTools({ agent, session, model, ... })

  // 4. 调用 LLM
  const result = await processor.process({
    system,
    messages: MessageV2.toModelMessages(msgs, model),  // ⭐ 转换消息格式
    tools,
    model,
  })

  // 5. 检查结果
  if (result === "stop") break
  if (result === "continue") continue  // 🔄 进入下一轮
}
```

### 消息增长的可视化

```
Token 使用随轮次增长：

Round 1:  [System: 4K] + [User: 0.5K] = 4.5K
              │
              ▼
Round 2:  [System: 4K] + [History: 2K] + [New: 1K] = 7K
              │                              │
              │                              └── AI 回复 + Tool Result
              │
              ▼
Round 3:  [System: 4K] + [History: 5K] + [New: 1K] = 10K
              │
              ▼
Round 4:  [System: 4K] + [History: 8K] + [New: 0.5K] = 12.5K

趋势：线性增长，直到触发 Compaction
```

### Compaction 时的变化

```
Compaction 前：
Messages: [msg1, msg2, msg3, msg4, msg5, msg6]  (150K tokens)

Compaction 后：
Messages: [summary_msg, msg6]  (20K tokens)
          │
          └── "之前我们完成了：1. 读取文件 2. 修改代码..."

System Prompt 不变，但上下文大幅压缩
```

### 图示：完整的迭代循环

```
┌─────────────────────────────────────────────────────────────────┐
│                         第 N 轮迭代                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  输入：                                                          │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ System: [环境, Provider, Skills, AGENTS.md]            │   │
│  │                                                        │   │
│  │ Messages: [                                            │   │
│  │   User: "帮我优化代码",                                 │   │
│  │   Assistant: "让我读取...",                             │   │
│  │   Tool: "文件内容...",                                  │   │
│  │   Assistant: "需要修改...",                             │   │
│  │   Tool: "编辑成功",     ← 上一轮的结果                   │   │
│  │ ]                                                      │   │
│  │                                                        │   │
│  │ Tools: [read, edit, bash, ...]                         │   │
│  └────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  LLM 处理                                                  │
│                           │                                     │
│                           ▼                                     │
│  输出：                                                         │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ Assistant: "让我测试一下..."                            │   │
│  │ Tool Calls: [{ name: "bash", ... }]                     │   │
│  └────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  执行工具                                                       │
│                           │                                     │
│                           ▼                                     │
│  保存到数据库：                                                  │
│  - 新的 Assistant 消息                                          │
│  - 新的 Tool Result 消息                                        │
│                           │                                     │
│                           ▼                                     │
│  result = "continue"                                         │
│                           │                                     │
│                           ▼                                     │
│  🔄 进入第 N+1 轮                                               │
│  （Messages 增加了两条）                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 总结

### 停止条件（优先级顺序）

```
1. 结构化输出完成（最高优先级）
2. 结构化输出失败（带错误退出）
3. 处理器返回 "stop"（blocked / error）
4. LLM finishReason 表示完成（stop/end_turn）
5. 达到最大步数限制（隐式，通过 step 计数器）
```

### 迭代变化

| 组件 | 是否变化 | 变化内容 |
|------|----------|----------|
| **System Prompt** | 轻微 | 环境信息（时间）可能更新 |
| **Messages** | ✅ 持续增长 | 追加 Assistant 消息 + Tool Results |
| **Tools** | 可能 | 权限变化或 MCP 状态变化 |
| **Model** | 否 | 同一会话保持相同模型 |
| **Agent** | 否 | 同一会话保持相同 Agent |

### 核心洞见

1. **System Prompt 是静态背景知识** - 告诉 AI "你是谁"
2. **Messages 是动态对话历史** - 告诉 AI "发生了什么"
3. **每一轮都重新组装** - 不是增量更新，而是完整重建
4. **消息增长是主要瓶颈** - 需要通过 Compaction 控制

---

**这就是 OpenCode 主循环的核心机制！** 🎯
