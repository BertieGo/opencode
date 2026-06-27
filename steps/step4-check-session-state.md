# Step 4: 检查会话状态 —— 内存告急时的"空间整理大师"

> **一句话总结**：检查对话历史是否太长（token 超限），如果"内存"不够了，就召唤 **compaction Agent** 来压缩历史，给新对话腾出空间。

---

## 🎬 场景回顾

前三步完成了：
1. ✅ **Step 1**：用户消息已打包
2. ✅ **Step 2**：确定使用 build Agent
3. ✅ **Step 3**：Agent 配置绑定到会话

现在进入主循环 `loop()`，**第一件事情**就是检查："我的'内存'还够吗？"

---

## 🧠 什么是"上下文溢出"？

LLM（大语言模型）有**固定的"记忆容量"**——上下文窗口（Context Window）：

| 模型 | 上下文限制 | 约等于 |
|------|-----------|--------|
| Claude 3.5 Sonnet | 200K tokens | 15万汉字 |
| GPT-4 | 128K tokens | 10万汉字 |
| GPT-3.5 | 16K tokens | 1.2万汉字 |

**Tokens 是什么？**
- 大约是 "单词片段"
- 1个汉字 ≈ 1-2 tokens
- 1个英文单词 ≈ 1-2 tokens

**溢出场景**：

```
场景A：正常使用
┌────────────────────────────────────────┐
│ 已用 175K tokens                       │
│ 新消息 5K tokens                       │
│ ─────────────────                      │
│ 总计 180K <= 200K 限制                 │
│                                        │
│ ✅ 安全，继续                           │
└────────────────────────────────────────┘

场景B：即将溢出
┌────────────────────────────────────────┐
│ 已用 195K tokens                       │
│ 新消息 10K tokens                      │
│ ─────────────────                      │
│ 总计 205K > 200K 限制                  │
│                                        │
│ ❌ 超限！需要压缩历史                    │
└────────────────────────────────────────┘
```

---

## 🔍 溢出检测机制

### 代码位置

```typescript
// packages/opencode/src/session/prompt.ts 第 545-555 行

if (
  lastFinished &&
  (await SessionCompaction.isOverflow({ tokens: lastFinished.tokens, model }))
) {
  // Token 超限了！创建压缩任务
  await SessionCompaction.create({
    sessionID,
    agent: lastUser.agent,
    model: lastUser.model,
    auto: true,
  })
  continue  // 重新开始循环，这次会处理压缩
}
```

### isOverflow 函数详解

```typescript
// packages/opencode/src/session/compaction.ts 第 33-49 行

const COMPACTION_BUFFER = 20_000  // 保留 20K tokens 的缓冲

export async function isOverflow(input: { 
  tokens: MessageV2.Assistant["tokens"]
  model: Provider.Model 
}) {
  const config = await Config.get()
  
  // 1. 用户可以在配置中关闭自动压缩
  if (config.compaction?.auto === false) return false
  
  // 2. 获取模型的上下文限制
  const context = input.model.limit.context
  if (context === 0) return false  // 无限制

  // 3. 计算已用 token 数
  const count =
    input.tokens.total ||
    input.tokens.input + 
    input.tokens.output + 
    input.tokens.cache.read + 
    input.tokens.cache.write

  // 4. 计算可用阈值（预留缓冲空间）
  const reserved = 
    config.compaction?.reserved ?? 
    Math.min(COMPACTION_BUFFER, ProviderTransform.maxOutputTokens(input.model))
  
  const usable = input.model.limit.input
    ? input.model.limit.input - reserved
    : context - ProviderTransform.maxOutputTokens(input.model)

  // 5. 判断是否超限
  return count >= usable
}
```

### 计算逻辑图解

```
模型上下文限制：200K tokens
         │
         ▼
┌─────────────────────────────────────────┐
│  实际可用空间 = 200K - 20K = 180K       │
│                                         │
│  ┌───────────────────────────────┐     │
│  │ 已用 tokens: 175K             │     │
│  │ ████████████████████░         │     │
│  │ 使用率：97%                   │     │
│  │ 状态：安全 ✅                 │     │
│  └───────────────────────────────┘     │
│                                         │
│  175K < 180K? 是 → 继续运行            │
│                                         │
│  如果 185K >= 180K? 否 → 触发压缩      │
└─────────────────────────────────────────┘
```

---

## 🗜️ 压缩过程（Compaction）

当检测到溢出时，系统会召唤 **compaction Agent** 来"整理空间"。

### 创建压缩任务

```typescript
// packages/opencode/src/session/compaction.ts 第 297-328 行

export const create = fn(
  z.object({
    sessionID: SessionID.zod,
    agent: z.string(),
    model: z.object({
      providerID: ProviderID.zod,
      modelID: ModelID.zod,
    }),
    auto: z.boolean(),         // 是否自动触发
    overflow: z.boolean().optional(),  // 是否已溢出
  }),
  async (input) => {
    // 创建一个特殊的"压缩请求"消息
    const msg = await Session.updateMessage({
      id: MessageID.ascending(),
      role: "user",
      model: input.model,
      sessionID: input.sessionID,
      agent: input.agent,
      time: { created: Date.now() },
    })
    
    // 添加 compaction 标记
    await Session.updatePart({
      id: PartID.ascending(),
      messageID: msg.id,
      sessionID: msg.sessionID,
      type: "compaction",
      auto: input.auto,
      overflow: input.overflow,
    })
  }
)
```

### 压缩处理流程

```typescript
// packages/opencode/src/session/compaction.ts 第 102-295 行

export async function process(input: {
  parentID: MessageID
  messages: MessageV2.WithParts[]
  sessionID: SessionID
  abort: AbortSignal
  auto: boolean
  overflow?: boolean
}) {
  // 1. 获取 compaction Agent
  const agent = await Agent.get("compaction")
  
  // 2. 确定使用哪个模型
  const model = agent.model
    ? await Provider.getModel(agent.model.providerID, agent.model.modelID)
    : await Provider.getModel(userMessage.model.providerID, userMessage.model.modelID)

  // 3. 创建 compaction 助理消息
  const msg = await Session.updateMessage({
    id: MessageID.ascending(),
    role: "assistant",
    parentID: input.parentID,
    sessionID: input.sessionID,
    mode: "compaction",
    agent: "compaction",
    summary: true,  // 标记为摘要消息
    // ...
  })

  // 4. 调用 LLM 生成摘要
  const result = await processor.process({
    messages: [
      ...MessageV2.toModelMessages(messages, model, { stripMedia: true }),
      {
        role: "user",
        content: [{
          type: "text",
          text: promptText,  // 让 AI 总结历史对话
        }],
      },
    ],
    // ...
  })

  // 5. 根据结果处理
  if (result === "compact") {
    // 压缩失败，历史还是太长
    processor.message.error = new MessageV2.ContextOverflowError({...})
    return "stop"
  }

  if (result === "continue" && input.auto) {
    // 压缩成功，创建"继续"消息
    await Session.updateMessage({...})
    await Session.updatePart({
      type: "text",
      text: "Continue if you have next steps...",
    })
  }
}
```

---

## 📝 压缩提示词（Prompt）

compaction Agent 使用特殊的提示词来指导 AI 如何总结：

```markdown
Provide a detailed prompt for continuing our conversation above.
Focus on information that would be helpful for continuing the conversation, 
including what we did, what we're doing, which files we're working on, 
and what we're going to do next.

The summary that you construct will be used so that another agent can 
read it and continue the work.

When constructing the summary, try to stick to this template:
---
## Goal
[What goal(s) is the user trying to accomplish?]

## Instructions
- [What important instructions did the user give you]
- [If there is a plan or spec, include information about it]

## Discoveries
[What notable things were learned during this conversation]

## Accomplished
[What work has been completed, what is in progress, what is left?]

## Relevant files / directories
[Construct a structured list of relevant files]
---
```

**压缩前后的对比**：

```
压缩前（原始对话历史）：
─────────────────────────────────────────
User: 帮我修复 bun test 报错
AI: 好的，让我先运行测试看看
[调用 bash: bun test]
[输出：错误堆栈 500行]

AI: 看起来是 sum 函数的问题，让我查看代码
[调用 read: src/sum.ts]
[文件内容 100行]

AI: 找到了，缺少 return 语句，让我修复
[调用 edit: src/sum.ts]
[修改内容]

AI: 修复完成，让我再测试一下
[调用 bash: bun test]
[输出：测试通过]

AI: 修复成功！sum 函数现在正确返回结果了。
─────────────────────────────────────────
总 tokens: 150K

压缩后（摘要）：
─────────────────────────────────────────
## Goal
修复 bun test 报错，sum 函数返回 undefined

## Instructions
- 运行测试定位错误
- 检查 sum.ts 文件
- 修复函数实现

## Discoveries
- sum 函数缺少 return 语句
- 错误导致测试失败

## Accomplished
- 运行测试，定位错误
- 读取 sum.ts，发现问题
- 修复函数，添加 return
- 重新测试，验证通过

## Relevant files
- src/sum.ts (已修复)
─────────────────────────────────────────
总 tokens: 2K

节省: 148K tokens (98.7%)
```

---

## 🌿 剪枝机制（Prune）

除了"压缩"（Compaction），还有一个更轻量的优化叫"剪枝"（Prune）：

```typescript
// packages/opencode/src/session/compaction.ts 第 51-100 行

export const PRUNE_MINIMUM = 20_000   // 至少剪 20K 才值得
export const PRUNE_PROTECT = 40_000   // 保护最近 40K 的上下文
export const PRUNE_PROTECTED_TOOLS = ["skill"]  // 保护 skill 工具

export async function prune(input: { sessionID: SessionID }) {
  const msgs = await Session.messages({ sessionID: input.sessionID })
  
  let total = 0
  let pruned = 0
  const toPrune = []
  
  // 从后往前遍历（最新的消息）
  for (let msgIndex = msgs.length - 1; msgIndex >= 0; msgIndex--) {
    const msg = msgs[msgIndex]
    
    // 只保护最近 2 轮对话
    if (msg.info.role === "user") turns++
    if (turns < 2) continue
    
    // 如果已经压缩过了，停止
    if (msg.info.role === "assistant" && msg.info.summary) break
    
    // 遍历消息的所有部分
    for (let partIndex = msg.parts.length - 1; partIndex >= 0; partIndex--) {
      const part = msg.parts[partIndex]
      
      // 找到已完成的工具调用
      if (part.type === "tool" && part.state.status === "completed") {
        // 保护特定工具
        if (PRUNE_PROTECTED_TOOLS.includes(part.tool)) continue
        
        // 计算这个工具输出的 token 数
        const estimate = Token.estimate(part.state.output)
        total += estimate
        
        // 如果超过了保护阈值，标记为可剪枝
        if (total > PRUNE_PROTECT) {
          pruned += estimate
          toPrune.push(part)
        }
      }
    }
  }
  
  // 如果剪枝能节省至少 20K，执行剪枝
  if (pruned > PRUNE_MINIMUM) {
    for (const part of toPrune) {
      part.state.time.compacted = Date.now()
      await Session.updatePart(part)
    }
  }
}
```

**压缩 vs 剪枝**：

| 特性 | Compaction（压缩） | Prune（剪枝） |
|------|-------------------|---------------|
| 触发时机 | token 接近上限时 | 每次 step 后自动 |
| 处理方式 | AI 总结生成摘要 | 删除旧工具输出 |
| 信息保留 | 高（结构化摘要） | 低（直接删除） |
| 触发 Agent | compaction Agent | 系统自动 |
| 节省空间 | 大（90%+） | 中等 |
| 副作用 | 需要 AI 处理 | 无 |

---

## 🎯 形象比喻总结

| 现实场景 | OpenCode Step 4 |
|---------|----------------|
| 检查手机存储空间 | isOverflow() 检测 |
| 存储空间不足警告 | token 数接近 limit |
| 整理相册腾出空间 | Compaction 压缩 |
| AI 帮你整理相册 | compaction Agent 总结 |
| 相册摘要代替原图 | 摘要文本代替原始对话 |
| 删除旧的缓存文件 | Prune 剪枝 |
| 保留最近的照片 | 保护最近 2 轮对话 |
| 手机清理大师 | SessionCompaction 模块 |

**完整场景**：

快递员张三（build Agent）准备出发，但发现他的"记忆背包"快满了（token 接近限制）。

他召唤了专业的"空间整理大师" compaction Agent 来帮忙：

1. 大师检查背包：已用 175K，还能用 5K，快满了！
2. 大师拿出一张羊皮纸，把背包里的旧文件快速浏览一遍
3. 大师在羊皮纸上写摘要：之前修好了 sum 函数，测试通过
4. 大师扔掉原始文件，只保留摘要
5. 背包腾出了 98% 的空间！
6. 张三可以继续执行任务了

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| 溢出检测 | packages/opencode/src/session/compaction.ts | 33-49 |
| 压缩处理 | packages/opencode/src/session/compaction.ts | 102-295 |
| 创建压缩任务 | packages/opencode/src/session/compaction.ts | 297-328 |
| 剪枝处理 | packages/opencode/src/session/compaction.ts | 59-100 |
| 循环中调用检测 | packages/opencode/src/session/prompt.ts | 545-555 |
| 调用 prune | packages/opencode/src/session/prompt.ts | 723 |

---

## 🚀 下一步

完成 Step 4 后，可能出现两种情况：
1. 无需压缩：token 充足，直接进入 Step 5（组装 System Prompt）
2. 已压缩：compaction Agent 完成摘要，重新循环，这次进入 Step 5

接下来进入 Step 5: 组装 System Prompt——准备发送给 LLM 的系统提示词。

准备好进入 Step 5 了吗？
