# Step 2: 确定使用哪个 Agent —— 派送员分配中心

> **一句话总结**：根据用户指定或系统默认，从**人才库**中挑选一个合适的 Agent（快递员），并给他配上**完整的装备清单**（权限配置）。

---

## 🎬 场景回顾

上一站，用户的"快递"（消息）已经打包完成：

```typescript
{
  role: "user",
  text: "我运行 bun test 报错了...",
  // ...其他元数据
}
```

现在，这个快递要交给谁来处理呢？就像顺丰要决定：这个包裹是交给**普通快递员**、**冷链专员**、还是**大宗货物司机**？

这就是 **Step 2** 要做的——**Agent 选择**。

---

## 🏢 派送员分配中心（Agent 系统架构）

```
┌─────────────────────────────────────────────────────────────────────┐
│                     OpenCode Agent 人才库                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   build      │  │    plan      │  │  general     │              │
│  │  ━━━━━━━━━   │  │  ━━━━━━━━━   │  │  ━━━━━━━━━   │              │
│  │  全能快递员   │  │  观察员      │  │  跑腿小弟     │              │
│  │  mode:primary│  │  mode:primary│  │  mode:subagent│             │
│  │  🔧 啥都能干  │  │  👀 只看不摸 │  │  🤝 被召唤   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  explore     │  │ compaction   │  │    title     │              │
│  │  ━━━━━━━━━   │  │  ━━━━━━━━━   │  │  ━━━━━━━━━   │              │
│  │  侦察兵      │  │  压缩员      │  │  命名师      │              │
│  │  mode:subagent│  │  mode:primary│  │  mode:primary│              │
│  │  🔍 专精搜索  │  │  hidden: true│  │  hidden: true│              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  ┌──────────────────────────────────────────────────┐              │
│  │              summary                             │              │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │              │
│  │              记录员                              │              │
│  │              mode:primary, hidden: true          │              │
│  │              📝 生成摘要                         │              │
│  └──────────────────────────────────────────────────┘              │
│                                                                      │
│  + 用户自定义 Agent（通过 opencode.yml 配置）                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 核心问题：选谁？

代码入口：

```typescript
// packages/opencode/src/session/prompt.ts 第 964 行

const agent = await Agent.get(input.agent ?? (await Agent.defaultAgent()))
```

这一行代码包含了**两步决策**：
1. 用户指定了 Agent 吗？`input.agent`
2. 没指定就用默认的：`Agent.defaultAgent()`

---

## 🔍 决策流程详解

### 情况一：用户指定了 Agent

用户在输入时明确说：

```
@plan 帮我看看这个代码库的结构
```

或者在代码中：
```typescript
prompt({
  sessionID: "sess_abc",
  agent: "plan",  // ⭐ 明确指定
  parts: [...]
})
```

这时候直接调用 `Agent.get("plan")`，从人才库中取出 plan Agent。

```typescript
// packages/opencode/src/agent/agent.ts 第 254-256 行

export async function get(agent: string) {
  return state().then((x) => x[agent])
}
```

**大白话**：就像你去快递点说"我要找张三帮我送"，系统就根据名字从员工名单里找到这个人。

---

### 情况二：用户没指定（默认选择）

大部分情况下，用户只是输入：
```
帮我修一下这个 bug
```

这时候就要走 `Agent.defaultAgent()` 逻辑：

```typescript
// packages/opencode/src/agent/agent.ts 第 267-282 行

export async function defaultAgent() {
  const cfg = await Config.get()          // 读取用户配置
  const agents = await state()            // 获取所有 Agent

  // 策略1：用户配置了默认 Agent？
  if (cfg.default_agent) {
    const agent = agents[cfg.default_agent]
    
    // 检查1：这个 Agent 存在吗？
    if (!agent) throw new Error(`default agent "${cfg.default_agent}" not found`)
    
    // 检查2：不能是 subagent（子 Agent 不能当默认）
    if (agent.mode === "subagent") 
      throw new Error(`default agent "${cfg.default_agent}" is a subagent`)
    
    // 检查3：不能是 hidden（隐藏 Agent 不能当默认）
    if (agent.hidden === true) 
      throw new Error(`default agent "${cfg.default_agent}" is hidden`)
    
    return agent.name
  }

  // 策略2：找第一个可见的 primary Agent
  const primaryVisible = Object.values(agents).find(
    (a) => a.mode !== "subagent" && a.hidden !== true
  )
  
  if (!primaryVisible) throw new Error("no primary visible agent found")
  return primaryVisible.name
}
```

**决策流程图**：

```
用户没指定 Agent
        │
        ▼
┌───────────────────┐
│ 读取配置文件      │
│ cfg.default_agent │
└─────────┬─────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
  有配置      没配置
    │           │
    ▼           ▼
┌────────┐  ┌─────────────────┐
│检查3条件│  │找第一个符合条件的│
│1.存在？ │  │primary Agent    │
│2.不是子？│  │（mode !== subagent│
│3.不隐藏？│  │ && hidden !== true）│
└───┬────┘  └────────┬────────┘
    │                │
    ▼                ▼
  通过            找到
    │                │
    └────────┬───────┘
             ▼
    返回 Agent 名称
    （通常是 "build"）
```

---

## 📦 人才库初始化（state 函数）

Agent 不是凭空出现的，而是在系统启动时初始化的。

```typescript
// packages/opencode/src/agent/agent.ts 第 52-252 行

const state = Instance.state(async () => {
  const cfg = await Config.get()          // 读取用户配置
  const skillDirs = await Skill.dirs()    // 获取技能目录
  
  // 1️⃣ 构建默认权限（所有 Agent 的基础装备）
  const whitelistedDirs = [Truncate.GLOB, ...skillDirs.map((dir) => path.join(dir, "*"))]
  const defaults = PermissionNext.fromConfig({
    "*": "allow",                         // 默认允许所有工具
    doom_loop: "ask",                     // 死循环检测需要询问
    external_directory: {                 // 外部目录访问权限
      "*": "ask",                         // 默认询问
      ...Object.fromEntries(whitelistedDirs.map((dir) => [dir, "allow"])),
    },
    question: "deny",                     // 默认不允许提问
    plan_enter: "deny",                   // 默认不允许进入 plan 模式
    plan_exit: "deny",                    // 默认不允许退出 plan 模式
    read: {                               // 读取权限特殊配置
      "*": "allow",
      "*.env": "ask",                    // .env 文件读取需要确认
      "*.env.*": "ask",
      "*.env.example": "allow",
    },
  })
  
  // 2️⃣ 读取用户配置的权限覆盖
  const user = PermissionNext.fromConfig(cfg.permission ?? {})

  // 3️⃣ 定义所有内置 Agent
  const result: Record<string, Info> = {
    build: { /* ... */ },
    plan: { /* ... */ },
    general: { /* ... */ },
    explore: { /* ... */ },
    compaction: { /* ... */ },
    title: { /* ... */ },
    summary: { /* ... */ },
  }
  
  // 4️⃣ 加载用户自定义 Agent
  for (const [key, value] of Object.entries(cfg.agent ?? {})) {
    // ...处理用户自定义配置
  }
  
  return result
})
```

**关键点**：`state()` 使用 `Instance.state()` 做懒加载（Lazy Initialization），第一次访问时才会初始化，之后缓存复用。

---

## 🛡️ 权限合并详解（三层叠加）

每个 Agent 的权限不是单独定义的，而是**三层叠加**的结果：

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Agent 专属规则（最具体）                    │
│  例：build Agent 允许 question                       │
│  例：plan Agent 禁止 edit                           │
├─────────────────────────────────────────────────────┤
│  Layer 2: 用户配置文件（~/.opencode/opencode.yml）   │
│  用户可以覆盖任何权限                                │
├─────────────────────────────────────────────────────┤
│  Layer 1: 默认规则（代码硬编码）                      │
│  所有工具默认 allow，但 question/plan 等默认 deny   │
└─────────────────────────────────────────────────────┘
```

### 代码示例：build Agent 的权限

```typescript
// packages/opencode/src/agent/agent.ts 第 78-92 行

build: {
  name: "build",
  description: "The default agent. Executes tools based on configured permissions.",
  options: {},
  permission: PermissionNext.merge(
    defaults,                              // ⬅️ Layer 1: 默认权限
    PermissionNext.fromConfig({            // ⬅️ Layer 3: build 专属
      question: "allow",                   //     build 允许提问
      plan_enter: "allow",                 //     build 允许切换到 plan
    }),
    user,                                  // ⬅️ Layer 2: 用户配置覆盖
  ),
  mode: "primary",
  native: true,
}
```

### 代码示例：plan Agent 的权限

```typescript
// packages/opencode/src/agent/agent.ts 第 93-115 行

plan: {
  name: "plan",
  description: "Plan mode. Disallows all edit tools.",
  options: {},
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      question: "allow",
      plan_exit: "allow",
      external_directory: {
        [path.join(Global.Path.data, "plans", "*")]: "allow",
      },
      edit: {
        "*": "deny",                       // ⭐ 关键：plan 禁止所有编辑！
        [path.join(".opencode", "plans", "*.md")]: "allow",
      },
    }),
    user,
  ),
  mode: "primary",
  native: true,
}
```

**大白话**：
- **build** = 全能快递员，啥都能干（能提问、能进 plan 模式）
- **plan** = 观察员，**只能看不能摸**（edit 全部 deny）

### 代码示例：explore Agent 的权限（白名单模式）

```typescript
// packages/opencode/src/agent/agent.ts 第 131-157 行

explore: {
  name: "explore",
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      "*": "deny",                         // ⭐ 先全部禁止
      grep: "allow",                       // 只允许搜索相关工具
      glob: "allow",
      list: "allow",
      bash: "allow",
      webfetch: "allow",
      websearch: "allow",
      codesearch: "allow",
      read: "allow",
    }),
    user,
  ),
  description: `Fast agent specialized for exploring codebases...`,
  prompt: PROMPT_EXPLORE,
  options: {},
  mode: "subagent",
  native: true,
}
```

**大白话**：explore 是**侦察兵**，只配备**侦察装备**（搜索工具），没有**武器**（编辑工具）。

---

## 🎭 Agent 的三种模式

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent 模式分类                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🎯 primary（主 Agent）                                          │
│     ├── 用户可以直接切换使用                                     │
│     ├── 例：build, plan                                          │
│     └── 特点：完整功能，面向用户                                 │
│                                                                  │
│  🔧 subagent（子 Agent）                                         │
│     ├── 只能被其他 Agent 召唤                                    │
│     ├── 例：general, explore                                     │
│     └── 特点：专注特定任务，并行执行                             │
│                                                                  │
│  👻 hidden（隐藏 Agent）                                         │
│     ├── 系统内部使用，用户看不到                                 │
│     ├── 例：compaction, title, summary                           │
│     └── 特点：自动化任务，幕后工作                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 用户自定义 Agent

用户可以在 `~/.opencode/opencode.yml` 中定义自己的 Agent：

```yaml
agent:
  my-custom-agent:
    name: "my-custom-agent"
    description: "专门处理文档的 Agent"
    mode: "primary"
    temperature: 0.7
    permission:
      edit:
        "*.md": "allow"       # 只允许编辑 markdown
        "*": "deny"           # 其他文件禁止编辑
      bash:
        "npm *": "allow"      # 只允许 npm 命令
        "*": "deny"
```

系统加载代码：

```typescript
// packages/opencode/src/agent/agent.ts 第 206-233 行

for (const [key, value] of Object.entries(cfg.agent ?? {})) {
  // 如果用户禁用了内置 Agent
  if (value.disable) {
    delete result[key]
    continue
  }
  
  let item = result[key]
  
  // 如果是新 Agent，创建基础结构
  if (!item)
    item = result[key] = {
      name: key,
      mode: "all",
      permission: PermissionNext.merge(defaults, user),
      options: {},
      native: false,  // 用户自定义的标记为 non-native
    }
  
  // 合并用户配置
  if (value.model) item.model = Provider.parseModel(value.model)
  item.variant = value.variant ?? item.variant
  item.prompt = value.prompt ?? item.prompt
  item.description = value.description ?? item.description
  item.temperature = value.temperature ?? item.temperature
  item.mode = value.mode ?? item.mode
  item.color = value.color ?? item.color
  item.hidden = value.hidden ?? item.hidden
  item.name = value.name ?? item.name
  item.steps = value.steps ?? item.steps
  item.permission = PermissionNext.merge(
    item.permission, 
    PermissionNext.fromConfig(value.permission ?? {})
  )
}
```

---

## 🎯 形象比喻总结

| 现实场景 | OpenCode Step 2 |
|---------|----------------|
| 快递点分派快递员 | `Agent.get()` / `Agent.defaultAgent()` |
| 查看员工名单 | `state()` 获取所有 Agent |
| 指定快递员 | `input.agent` 参数 |
| 默认派单规则 | `defaultAgent()` 三条件检查 |
| 员工基础装备 | `defaults` 默认权限 |
| 岗位专属装备 | Agent 专属权限配置 |
| 个人定制装备 | 用户配置 `cfg.permission` |
| 新员工入职 | 用户自定义 Agent |
| 岗位分类（快递员/司机/分拣员）| Agent mode（primary/subagent/hidden）|

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| 获取指定 Agent | `packages/opencode/src/agent/agent.ts` | 254-256 |
| 获取默认 Agent | `packages/opencode/src/agent/agent.ts` | 267-282 |
| Agent 状态初始化 | `packages/opencode/src/agent/agent.ts` | 52-252 |
| build Agent 定义 | `packages/opencode/src/agent/agent.ts` | 78-92 |
| plan Agent 定义 | `packages/opencode/src/agent/agent.ts` | 93-115 |
| general Agent 定义 | `packages/opencode/src/agent/agent.ts` | 116-130 |
| explore Agent 定义 | `packages/opencode/src/agent/agent.ts` | 131-157 |
| 隐藏 Agents 定义 | `packages/opencode/src/agent/agent.ts` | 158-204 |
| 用户自定义加载 | `packages/opencode/src/agent/agent.ts` | 206-233 |
| Agent Info Schema | `packages/opencode/src/agent/agent.ts` | 25-50 |

---

## 🚀 下一步

完成 Step 2 后，系统已经确定了：
1. ✅ 使用哪个 Agent（如：build）
2. ✅ Agent 的完整配置（权限、模型、提示词等）

接下来进入 **Step 3: 加载 Agent 配置**，把 Agent 的配置和权限应用到当前会话。

准备好进入 **Step 3** 了吗？
