# Step 3: 加载 Agent 配置 —— 装备检查与权限生效

> **一句话总结**：把选定的 Agent 配置**应用到当前会话**，完成权限的最终合并，并准备好进入主循环的**所有前置条件**。

---

## 🎬 场景回顾

前两步完成了：
1. ✅ **Step 1**：用户消息已打包完成（快递已收件）
2. ✅ **Step 2**：确定了使用哪个 Agent（已分派快递员 build）

现在进入 **Step 3**：给这个快递员**发放装备**，让他准备出发！

---

## 🎒 装备发放流程

```
Agent 配置（已确定）                    会话（当前状态）
┌─────────────────────┐              ┌─────────────────────┐
│  name: "build"      │              │  id: "sess_abc"     │
│  mode: "primary"    │   ═══════►   │  permission: []     │
│  permission: [...]  │    应用配置   │  agent: "build" ◄───┼── 绑定
│  model: {...}       │              │  model: {...} ◄─────┼── 绑定
│  prompt: "..."      │              │  status: "ready"    │
└─────────────────────┘              └─────────────────────┘
                                            │
                                            ▼
                                     进入主循环 loop()
```

---

## 🔧 代码层面的"装备发放"

### 1️⃣ 旧版工具权限兼容处理

```typescript
// packages/opencode/src/session/prompt.ts 第 167-180 行

// this is backwards compatibility for allowing `tools` to be specified when
// prompting
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
```

**大白话**：这是为了兼容旧版本的 API。以前可以在发送消息时临时指定工具权限，现在虽然主要通过 Agent 配置，但还保留了这个入口。

**什么时候用？**
```typescript
// 用户这样调用时
prompt({
  sessionID: "sess_abc",
  tools: {          // ⭐ 临时指定工具权限
    bash: true,     // 允许 bash
    edit: false,    // 禁止 edit
  },
  parts: [...]
})
```

**现代用法**：直接在 Agent 配置里定义权限，不需要这里临时指定。

---

### 2️⃣ 消息对象的 Agent 绑定（在 Step 1 中完成）

回顾 Step 1 的关键代码：

```typescript
// packages/opencode/src/session/prompt.ts 第 973-986 行

const info: MessageV2.Info = {
  id: input.messageID ?? MessageID.ascending(),
  role: "user",
  sessionID: input.sessionID,
  time: { created: Date.now() },
  tools: input.tools,           // ⭐ 旧版工具配置（兼容）
  agent: agent.name,            // ⭐⭐ 绑定选定的 Agent！
  model,                        // ⭐⭐ 绑定选定的模型！
  system: input.system,
  format: input.format,
  variant,
}
```

**关键点**：用户消息对象里已经写死了要使用的 Agent 和模型，这就相当于给这个"快递包裹"贴上了"指定由 build 处理"的标签。

---

### 3️⃣ 进入主循环前的状态检查

```typescript
// packages/opencode/src/session/prompt.ts 第 182-186 行

// 如果设置了 noReply，只保存消息不进入主循环
if (input.noReply === true) {
  return message
}

// 进入主循环
return loop({ sessionID: input.sessionID })
```

**大白话**：
- `noReply = true`：只存档，不处理（像发了一封邮件但不需要回复）
- `noReply = false`（默认）：正常进入主循环处理

---

## 🔄 主循环开始时的配置提取

当 `loop()` 被调用后，第一件事情就是**从消息历史中还原配置**：

```typescript
// packages/opencode/src/session/prompt.ts 第 276-350 行

export const loop = fn(LoopInput, async (input) => {
  const { sessionID, resume_existing } = input

  // 1. 初始化/恢复会话状态
  const abort = resume_existing ? resume(sessionID) : start(sessionID)
  if (!abort) {
    // 会话已在进行中，加入等待队列
    return new Promise<MessageV2.WithParts>((resolve, reject) => {
      const callbacks = state()[sessionID].callbacks
      callbacks.push({ resolve, reject })
    })
  }

  // 2. 设置清理钩子（函数结束时自动清理）
  using _ = defer(() => cancel(sessionID))

  // 3. 进入主循环
  let step = 0
  const session = await Session.get(sessionID)
  
  while (true) {
    SessionStatus.set(sessionID, { type: "busy" })
    
    // 4. 获取消息历史
    let msgs = await MessageV2.filterCompacted(MessageV2.stream(sessionID))

    // 5. ⭐⭐⭐ 从消息历史中提取关键信息
    let lastUser: MessageV2.User | undefined
    let lastAssistant: MessageV2.Assistant | undefined
    
    for (let i = msgs.length - 1; i >= 0; i--) {
      const msg = msgs[i]
      if (!lastUser && msg.info.role === "user") 
        lastUser = msg.info as MessageV2.User
      if (!lastAssistant && msg.info.role === "assistant") 
        lastAssistant = msg.info as MessageV2.Assistant
      if (lastUser && lastAssistant) break
    }

    if (!lastUser) throw new Error("No user message found...")

    // 6. ⭐⭐⭐ 从最新消息中提取 Agent 和模型配置
    const model = await Provider.getModel(
      lastUser.model.providerID, 
      lastUser.model.modelID
    )
    
    // 7. 检查是否需要生成标题（第一次迭代）
    step++
    if (step === 1)
      ensureTitle({
        session,
        modelID: lastUser.model.modelID,
        providerID: lastUser.model.providerID,
        history: msgs,
      })
    
    // ... 继续处理
  }
})
```

**关键点解析**：

### `lastUser` 对象包含什么？

```typescript
// 从消息历史中提取的最后一个用户消息
lastUser = {
  id: "msg_001",
  role: "user",
  sessionID: "sess_abc",
  agent: "build",                    // ⭐ 要使用的 Agent
  model: {                          // ⭐ 要使用的模型
    providerID: "anthropic",
    modelID: "claude-3-5-sonnet-20241022"
  },
  format: undefined,                // 输出格式要求
  variant: undefined,               // 模型变体
  // ... 其他字段
}
```

---

## 🎯 权限的最终生效

Agent 的权限配置在哪里真正被使用？

### 在工具执行时检查权限

```typescript
// packages/opencode/src/session/prompt.ts 第 785 行附近

// 当 LLM 决定调用工具时
ruleset: PermissionNext.merge(
  input.agent.permission,           // ⭐ Agent 配置的权限
  input.session.permission ?? []    // ⭐ 会话级别的权限覆盖
)
```

**大白话**：工具执行时，会把 Agent 的权限和会话的权限合并，最终决定这个工具调用是否被允许。

### 权限合并的优先级（最终版）

```
实际执行时的权限 = 
  Agent 配置权限
  + 会话权限（如果有）
  + 动态检查（如 .env 文件询问）

优先级（高到低）：
1. 动态规则（如 doom_loop 检测）
2. 具体文件匹配（如 "*.env": "ask"）
3. 会话级别覆盖
4. Agent 专属配置
5. 默认配置
```

---

## 🏗️ 整体架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Step 3: 加载 Agent 配置                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Step 1 的产出              Step 2 的产出                             │
│  ┌──────────────┐          ┌──────────────┐                          │
│  │  Message     │          │  Agent Info  │                          │
│  │  (已打包)    │          │  (build)     │                          │
│  └──────┬───────┘          └──────┬───────┘                          │
│         │                         │                                  │
│         └──────────┬──────────────┘                                  │
│                    ▼                                                 │
│            ┌──────────────┐                                          │
│            │  createUser  │                                          │
│            │  Message()   │                                          │
│            └──────┬───────┘                                          │
│                   │                                                  │
│                   ▼                                                  │
│     ┌─────────────────────────┐                                      │
│     │  绑定 Agent & Model     │                                      │
│     │  agent: agent.name      │                                      │
│     │  model: model           │                                      │
│     └───────────┬─────────────┘                                      │
│                 │                                                    │
│                 ▼                                                    │
│     ┌─────────────────────────┐                                      │
│     │  写入数据库             │                                      │
│     │  MessageV2.insert()     │                                      │
│     └───────────┬─────────────┘                                      │
│                 │                                                    │
│                 ▼                                                    │
│     ┌─────────────────────────┐                                      │
│     │  检查 noReply?          │                                      │
│     │  false → 进入 loop()    │                                      │
│     └───────────┬─────────────┘                                      │
│                 │                                                    │
│                 ▼                                                    │
│     ┌─────────────────────────┐                                      │
│     │  loop() 提取配置        │                                      │
│     │  lastUser.agent         │                                      │
│     │  lastUser.model         │                                      │
│     └───────────┬─────────────┘                                      │
│                 │                                                    │
│                 ▼                                                    │
│     ┌─────────────────────────┐                                      │
│     │  配置就绪，开始处理     │                                      │
│     │  Step 4: 检查会话状态   │                                      │
│     └─────────────────────────┘                                      │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🎭 形象比喻：快递员出车前检查

| 现实场景 | OpenCode Step 3 |
|---------|----------------|
| 确认快递员身份 | `lastUser.agent` |
| 确认车辆型号 | `lastUser.model` |
| 发放工作装备 | `Agent.permission` |
| 特殊任务许可 | `session.permission`（会话级覆盖） |
| 检查车辆状态 | `Provider.getModel()` |
| 出车登记 | `loop()` 开始 |
| 待命状态 | `noReply = true` 直接返回 |

**完整场景**：

> 快递分拣中心（OpenCode）收到一个包裹（用户消息），已经确定了由**张三**（build Agent）负责派送。现在要进行**出车前的装备检查**：
> 
> 1. 给张三发放标准装备包（Agent 权限配置）
> 2. 检查是否有特殊任务要求（会话权限覆盖）
> 3. 确认派送车辆型号（model 配置）
> 4. 检查车辆状态正常（`Provider.getModel()`）
> 5. 如果不是"仅存档"任务（`noReply`），张三就出发开始派送（进入 `loop()`）

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| 旧版权限兼容 | `packages/opencode/src/session/prompt.ts` | 167-180 |
| 消息中绑定 Agent | `packages/opencode/src/session/prompt.ts` | 981-982 |
| 主循环入口 | `packages/opencode/src/session/prompt.ts` | 276-286 |
| 提取 lastUser | `packages/opencode/src/session/prompt.ts` | 302-319 |
| 获取模型实例 | `packages/opencode/src/session/prompt.ts` | 338-349 |
| 权限合并执行 | `packages/opencode/src/session/prompt.ts` | 785-786 |
| 生成标题检查 | `packages/opencode/src/session/prompt.ts` | 330-336 |

---

## 💡 容易混淆的概念澄清

### Q1: Agent 权限 vs 会话权限，有什么区别？

```
Agent 权限（Agent.permission）
├── 定义在 Agent 配置中
├── 每个 Agent 有自己的权限规则
└── 例：build 允许 question，plan 禁止 edit

会话权限（session.permission）
├── 定义在特定会话中
├── 可以临时覆盖 Agent 权限
└── 例：这个会话临时禁止 bash

实际执行 = Agent 权限 + 会话权限（合并）
```

### Q2: 为什么要在消息里存 agent 和 model？

```typescript
// 用户消息中存储
agent: "build"
model: { providerID: "anthropic", modelID: "claude-3-5" }
```

**原因**：
1. **追溯性**：知道这条消息是用什么 Agent 处理的
2. **恢复性**：会话恢复时能正确还原配置
3. **灵活性**：不同消息可以用不同 Agent/模型

### Q3: noReply 模式有什么用？

场景举例：
- 用户只是想**存档一条消息**，不需要 AI 回复
- 系统后台**插入系统消息**，不需要触发处理
- 批处理时**先存消息**，稍后统一处理

---

## 🚀 下一步

完成 Step 3 后，系统已经：
1. ✅ Agent 配置绑定到消息
2. ✅ 进入主循环 `loop()`
3. ✅ 提取了最新的 Agent 和模型配置

接下来进入 **Step 4: 检查会话状态**——检测上下文是否溢出，是否需要压缩。

准备好进入 **Step 4** 了吗？
