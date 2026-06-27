# Step 5: 组装 System Prompt —— AI 的"入职培训手册"

> **一句话总结**：把环境信息、模型特定指令、项目特定说明和技能介绍组装成一份完整的"入职手册"，告诉 AI 它是谁、在哪、能干什么、该怎么干活。

---

## 🎬 场景回顾

前四步完成了：
1. ✅ **Step 1**：用户消息已打包
2. ✅ **Step 2**：确定使用 build Agent
3. ✅ **Step 3**：Agent 配置绑定到会话
4. ✅ **Step 4**：检查并压缩会话状态

现在万事俱备，要开始和 AI 对话了！但在这之前，需要先给 AI 一份**详细的"入职培训手册"**——这就是 System Prompt。

---

## 📚 什么是 System Prompt？

System Prompt（系统提示词）是发送给 LLM 的**第一段消息**，它：
- 定义 AI 的**角色**（你是什么）
- 告诉 AI **环境信息**（你在哪）
- 说明**可用工具**（你有什么）
- 规定**行为准则**（你该怎么做）

**类比**：
- 就像给新员工发一本《员工手册》
- 就像给演员一份《角色设定和剧本说明》
- 就像给司机一张《路线图和驾驶规范》

---

## 🧩 System Prompt 的四层结构

OpenCode 的 System Prompt 由四个部分组成：

```
┌─────────────────────────────────────────────────────────────────┐
│                    System Prompt 结构                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: 环境信息 (Environment)                                 │
│  ├── 你是谁："You are powered by Claude 3.5 Sonnet"             │
│  ├── 你在哪："Working directory: /Users/.../my-project"         │
│  ├── 什么系统："Platform: darwin"                               │
│  └── 今天几号："Today's date: Mon Mar 17 2025"                  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 2: 模型特定提示 (Provider)                                │
│  ├── Claude → anthropic.txt（强调任务管理、TodoWrite）          │
│  ├── GPT → beast.txt（强调研究、递归 webfetch）                 │
│  ├── Gemini → gemini.txt（Gemini 特定优化）                     │
│  └── Codex → codex_header.txt（前端/Git 安全）                  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 3: 项目特定指令 (Instructions)                            │
│  ├── AGENTS.md（项目级 Agent 配置）                             │
│  ├── CLAUDE.md（Claude Code 兼容配置）                          │
│  └── 用户自定义 instructions                                    │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 4: 技能介绍 (Skills)                                      │
│  ├── 可用技能列表                                               │
│  └── 如何使用 Skill 工具加载                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 代码实现详解

### 组装入口

```typescript
// packages/opencode/src/session/prompt.ts 第 654-659 行

const skills = await SystemPrompt.skills(agent)
const system = [
  ...(await SystemPrompt.environment(model)),      // ⭐ Layer 1: 环境
  ...(skills ? [skills] : []),                      // ⭐ Layer 4: 技能
  ...(await InstructionPrompt.system()),            // ⭐ Layer 3: 项目指令
]

// 然后会把 system 数组和 provider 提示词合并发送
```

### Layer 1: 环境信息 (environment)

```typescript
// packages/opencode/src/session/system.ts 第 32-57 行

export async function environment(model: Provider.Model) {
  const project = Instance.project
  return [
    [
      // 告诉 AI 它是什么模型
      `You are powered by the model named ${model.api.id}. The exact model ID is ${model.providerID}/${model.api.id}`,
      
      // 环境信息标题
      `Here is some useful information about the environment you are running in:`,
      
      // XML 格式的环境变量
      `<env>`,
      `  Working directory: ${Instance.directory}`,        // 当前工作目录
      `  Workspace root folder: ${Instance.worktree}`,     // 项目根目录
      `  Is directory a git repo: ${project.vcs === "git" ? "yes" : "no"}`,
      `  Platform: ${process.platform}`,                   // 操作系统
      `  Today's date: ${new Date().toDateString()}`,      // 今天日期
      `</env>`,
      
      // 目录结构（暂时禁用）
      `<directories>`,
      `  ${project.vcs === "git" && false ? await Ripgrep.tree({...}) : ""}`,
      `</directories>`,
    ].join("\n"),
  ]
}
```

**示例输出**：
```markdown
You are powered by the model named claude-3-5-sonnet-20241022. The exact model ID is anthropic/claude-3-5-sonnet-20241022
Here is some useful information about the environment you are running in:
<env>
  Working directory: /Users/alice/projects/my-app
  Workspace root folder: /Users/alice/projects/my-app
  Is directory a git repo: yes
  Platform: darwin
  Today's date: Mon Mar 17 2025
</env>
<directories>
</directories>
```

---

### Layer 2: 模型特定提示 (provider)

不同模型有不同的特性，OpenCode 准备了不同的提示词：

```typescript
// packages/opencode/src/session/system.ts 第 22-30 行

export function provider(model: Provider.Model) {
  // GPT-5 系列 → 使用 Codex 提示词（前端/Git 安全）
  if (model.api.id.includes("gpt-5")) return [PROMPT_CODEX]
  
  // GPT-4/3.5、o1、o3 → 使用 Beast 提示词（研究型、递归 webfetch）
  if (model.api.id.includes("gpt-") || 
      model.api.id.includes("o1") || 
      model.api.id.includes("o3"))
    return [PROMPT_BEAST]
  
  // Gemini → Gemini 专用提示词
  if (model.api.id.includes("gemini-")) return [PROMPT_GEMINI]
  
  // Claude → Anthropic 提示词（强调任务管理）
  if (model.api.id.includes("claude")) return [PROMPT_ANTHROPIC]
  
  // Trinity → Trinity 专用
  if (model.api.id.toLowerCase().includes("trinity")) return [PROMPT_TRINITY]
  
  // 默认 → 不带 TodoWrite 的提示词（给不支持工具的模型）
  return [PROMPT_ANTHROPIC_WITHOUT_TODO]
}
```

#### Claude 提示词特点（anthropic.txt）

```markdown
You are OpenCode, the best coding agent on the planet.

You are an interactive CLI tool that helps users with software engineering tasks.

# Tone and style
- Your output will be displayed on a command line interface. Your responses should be short and concise.
- Only use emojis if the user explicitly requests it.

# Task Management ⭐⭐⭐
You have access to the TodoWrite tools to help you manage and plan tasks. 
Use these tools VERY frequently...
It is critical that you mark todos as completed as soon as you are done with a task.

# Tool usage policy
- When doing file search, prefer to use the Task tool in order to reduce context usage.
- Use specialized tools instead of bash commands when possible.
- Use the Read tool for reading files instead of cat/head/tail.
- Use the Edit tool for editing instead of sed/awk.
```

**重点**：
- 强调 **TodoWrite** 工具的使用（Claude 擅长任务管理）
- 强调使用专门的 **Task 工具**而不是直接搜索
- 强调 **CLI 输出要简洁**

#### GPT 提示词特点（beast.txt）

```markdown
You must use the webfetch tool to recursively gather all information 
from URL's provided to you by the user...

Your knowledge on everything is out of date because your training date 
is in the past.

Research-driven, autonomous, thorough workflow.
```

**重点**：
- 强调 **递归使用 webfetch**（GPT 擅长研究和信息收集）
- 承认知识有截止日期
- 鼓励自主、深入的研究

#### Codex 提示词特点（codex_header.txt）

```markdown
# Web app development rules
1. NEVER guess or generate URLs... 
2. The dev server has already been started for you...
3. NEVER run git commands...

# Output format
When you send edits, the code will be formatted in the terminal.
```

**重点**：
- **前端开发专用**
- 强调 **不要猜测 URL**
- 强调 **Git 安全**（不要运行 git 命令）

---

### Layer 3: 项目特定指令 (InstructionPrompt)

OpenCode 会自动查找并加载项目中的指令文件：

```typescript
// packages/opencode/src/session/instruction.ts 第 14-30 行

const FILES = [
  "AGENTS.md",      // ⭐ OpenCode 专用配置
  "CLAUDE.md",      // Claude Code 兼容配置
  "CONTEXT.md",     // 已废弃
]

function globalFiles() {
  const files = []
  // 1. 环境变量指定的配置目录
  if (Flag.OPENCODE_CONFIG_DIR) {
    files.push(path.join(Flag.OPENCODE_CONFIG_DIR, "AGENTS.md"))
  }
  // 2. 全局配置目录
  files.push(path.join(Global.Path.config, "AGENTS.md"))
  // 3. Claude Code 兼容（如果不禁用）
  if (!Flag.OPENCODE_DISABLE_CLAUDE_CODE_PROMPT) {
    files.push(path.join(os.homedir(), ".claude", "CLAUDE.md"))
  }
  return files
}
```

#### 查找逻辑

```typescript
// packages/opencode/src/session/instruction.ts 第 72-115 行

export async function systemPaths() {
  const config = await Config.get()
  const paths = new Set<string>()

  // 1. 查找项目中的指令文件（向上遍历目录）
  if (!Flag.OPENCODE_DISABLE_PROJECT_CONFIG) {
    for (const file of FILES) {
      const matches = await Filesystem.findUp(file, Instance.directory, Instance.worktree)
      if (matches.length > 0) {
        matches.forEach((p) => paths.add(path.resolve(p)))
        break  // 找到第一个就停
      }
    }
  }

  // 2. 查找全局指令文件
  for (const file of globalFiles()) {
    if (await Filesystem.exists(file)) {
      paths.add(path.resolve(file))
      break
    }
  }

  // 3. 加载用户配置中的 instructions
  if (config.instructions) {
    for (let instruction of config.instructions) {
      // 支持 URL、绝对路径、相对路径
      if (instruction.startsWith("https://") || instruction.startsWith("http://")) {
        // URL 会在后面 fetch
      } else {
        // 解析路径...
      }
    }
  }

  return paths
}
```

#### 实际加载

```typescript
// packages/opencode/src/session/instruction.ts 第 117-142 行

export async function system() {
  const config = await Config.get()
  const paths = await systemPaths()

  // 读取本地文件
  const files = Array.from(paths).map(async (p) => {
    const content = await Filesystem.readText(p).catch(() => "")
    return content ? "Instructions from: " + p + "\n" + content : ""
  })

  // 获取 URL 指令
  const urls: string[] = []
  if (config.instructions) {
    for (const instruction of config.instructions) {
      if (instruction.startsWith("https://") || instruction.startsWith("http://")) {
        urls.push(instruction)
      }
    }
  }
  
  // 并行获取所有 URL
  const fetches = urls.map((url) =>
    fetch(url, { signal: AbortSignal.timeout(5000) })
      .then((res) => (res.ok ? res.text() : ""))
      .catch(() => "")
      .then((x) => (x ? "Instructions from: " + url + "\n" + x : "")),
  )

  return Promise.all([...files, ...fetches]).then((result) => result.filter(Boolean))
}
```

**示例**：假设项目根目录有 `AGENTS.md`

```markdown
# AGENTS.md

## 项目结构

- `/packages/core` - 核心逻辑
- `/packages/ui` - UI 组件
- `/apps/web` - Web 应用

## 编码规范

1. 使用 TypeScript
2. 优先使用函数组件
3. 测试文件放在 `__tests__` 目录

## 常用命令

- `bun dev` - 启动开发服务器
- `bun test` - 运行测试
- `bun build` - 构建项目
```

这些指令会被加载到 System Prompt 中，让 AI 了解项目特定的信息。

---

### Layer 4: 技能介绍 (skills)

```typescript
// packages/opencode/src/session/system.ts 第 59-71 行

export async function skills(agent: Agent.Info) {
  // 检查 Agent 是否有 skill 权限
  if (PermissionNext.disabled(["skill"], agent.permission).has("skill")) 
    return

  // 获取可用技能列表
  const list = await Skill.available(agent)

  return [
    "Skills provide specialized instructions and workflows for specific tasks.",
    "Use the skill tool to load a skill when a task matches its description.",
    Skill.fmt(list, { verbose: true }),  // 格式化技能列表
  ].join("\n")
}
```

**示例输出**：
```markdown
Skills provide specialized instructions and workflows for specific tasks.
Use the skill tool to load a skill when a task matches its description.

Available skills:

1. **explain-code** - Explain how code works in detail
   Usage: Use when trying to understand unfamiliar code, complex logic, or system architecture.

2. **content-summarizer** - Fetch and summarize web content
   Usage: Use for articles, GitHub repos, Reddit/HN/Twitter threads.

3. **frontend-design** - Create production-grade frontend interfaces
   Usage: Use when building web components, pages, dashboards.
```

---

## 🎯 完整的 System Prompt 示例

把所有层组合起来，一个完整的 System Prompt 长这样：

```markdown
================================================================================
Layer 1: Environment
================================================================================
You are powered by the model named claude-3-5-sonnet-20241022. 
The exact model ID is anthropic/claude-3-5-sonnet-20241022
Here is some useful information about the environment you are running in:
<env>
  Working directory: /Users/alice/projects/my-app
  Workspace root folder: /Users/alice/projects/my-app
  Is directory a git repo: yes
  Platform: darwin
  Today's date: Mon Mar 17 2025
</env>
<directories>
</directories>

================================================================================
Layer 2: Provider (anthropic.txt)
================================================================================
You are OpenCode, the best coding agent on the planet.

You are an interactive CLI tool that helps users with software engineering tasks. 

# Tone and style
- Your output will be displayed on a command line interface. 
  Your responses should be short and concise.
- Only use emojis if the user explicitly requests it.

# Task Management
You have access to the TodoWrite tools to help you manage and plan tasks. 
Use these tools VERY frequently...

# Tool usage policy
- When doing file search, prefer to use the Task tool...
- Use specialized tools instead of bash commands when possible...

================================================================================
Layer 3: Instructions (AGENTS.md)
================================================================================
Instructions from: /Users/alice/projects/my-app/AGENTS.md

# AGENTS.md

## 项目结构
- `/packages/core` - 核心逻辑
- `/packages/ui` - UI 组件
...

================================================================================
Layer 4: Skills
================================================================================
Skills provide specialized instructions and workflows for specific tasks.
Use the skill tool to load a skill when a task matches its description.

Available skills:
1. **explain-code** - Explain how code works in detail
2. **content-summarizer** - Fetch and summarize web content
...
```

---

## 🎭 形象比喻总结

| 现实场景 | OpenCode Step 5 |
|---------|----------------|
| 新员工入职 | 组装 System Prompt |
| 公司介绍（你是谁/在哪） | Environment 层 |
| 岗位说明书（你该怎么做） | Provider 提示词 |
| 部门规章制度 | Instructions（AGENTS.md）|
| 可用工具清单 | Skills 层 |
| 入职培训手册装订 | 数组拼接 [...] |

**完整场景**：

> 快递员张三（build Agent）准备出发送快递。在他出发前，公司给他发了一本**《员工手册》**：
> 
> 1. **扉页**：介绍他使用的交通工具（Claude 3.5 Sonnet）
> 2. **第一章**：公司地址、仓库位置、今天是几号
> 3. **第二章**：岗位说明书（Claude 版）- 强调任务管理、使用专业工具
> 4. **第三章**：部门特殊规定（项目 AGENTS.md）- 项目结构、编码规范
> 5. **第四章**：可用工具清单（Skills）- 什么情况下用什么技能
>
> 张三带着这本手册，就可以专业地开始工作了！

---

## 💡 关键设计思想

### 1. 分层设计的好处
- **关注点分离**：每层只负责一部分
- **灵活组合**：不同 Agent 可以用不同的 Provider 提示词
- **易于扩展**：新增模型只需加一个新的 .txt 文件

### 2. 模型特定提示的必要性
不同模型有不同"性格"：
- **Claude**：喜欢结构化、任务列表
- **GPT**：喜欢研究、探索、递归获取信息
- **Gemini**：有自己的特殊格式偏好

给每个模型"定制化"的提示词，能发挥它们最大的优势。

### 3. 项目指令的动态加载
- AGENTS.md 放在项目里，版本控制一起管理
- 向上查找，支持 monorepo 子项目有不同配置
- 支持 URL，可以加载远程指令

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| System Prompt 组装 | `packages/opencode/src/session/prompt.ts` | 654-659 |
| 环境信息 | `packages/opencode/src/session/system.ts` | 32-57 |
| 模型选择提示词 | `packages/opencode/src/session/system.ts` | 22-30 |
| 技能介绍 | `packages/opencode/src/session/system.ts` | 59-71 |
| 项目指令加载 | `packages/opencode/src/session/instruction.ts` | 72-142 |
| Claude 提示词 | `packages/opencode/src/session/prompt/anthropic.txt` | 全文 |
| GPT 提示词 | `packages/opencode/src/session/prompt/beast.txt` | 全文 |
| Codex 提示词 | `packages/opencode/src/session/prompt/codex_header.txt` | 全文 |
| Gemini 提示词 | `packages/opencode/src/session/prompt/gemini.txt` | 全文 |

---

## 🚀 下一步

完成 Step 5 后，System Prompt 已经组装完毕。接下来进入 **Step 6: 组装可用工具列表**——告诉 AI 它有什么工具可以用。

准备好进入 **Step 6** 了吗？
