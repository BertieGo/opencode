# Agent vs Skill vs Tool vs MCP：设计边界与选择指南

> 深入解析 OpenCode 的四种扩展机制，用生动的比喻帮你理解何时使用什么。

---

## 🎭 核心比喻：一家 AI 软件外包公司

想象你经营一家软件外包公司，面对不同类型的需求，你需要决定：

- **派遣整个团队**（Agent）
- **给现有团队配备专家手册**（Skill）
- **使用现成工具**（Tool）
- **调用外部服务商**（MCP）

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenCode 外包公司架构                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  👤 项目经理（主 Agent）                                         │
│     ├── 手下有多支专业团队（Subagents）                          │
│     ├── 拥有各种工具（Tools）                                    │
│     └── 可以随时请外部专家（Skills）或外包商（MCP）              │
│                                                                  │
│  🏢 内部专业团队（Agents）                                       │
│     ├── 🔨 Build 施工队 - 全能开发                              │
│     ├── 📝 Plan 规划组 - 只读规划                               │
│     ├── 🔍 Explore 侦察组 - 代码探索专家                        │
│     └── 🧰 General 特勤组 - 多任务并行                          │
│                                                                  │
│  🛠️ 工具库（Tools）                                              │
│     ├── Read/Glob/Grep - 文件工具                               │
│     ├── Edit/Write - 编辑工具                                   │
│     ├── Bash - 命令行工具                                       │
│     ├── Task - 团队派遣工具                                     │
│     └── Skill - 专家手册加载工具                                │
│                                                                  │
│  📚 专家手册库（Skills）                                         │
│     ├── PPTX 专家 - 演示文稿制作                                │
│     ├── XLSX 专家 - 电子表格处理                                │
│     └── WebApp Testing 专家 - 网页测试                          │
│                                                                  │
│  🔌 外部服务商（MCP Servers）                                    │
│     ├── 数据库服务商                                            │
│     ├── 搜索引擎服务商                                          │
│     └── 企业内网 API                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1️⃣ Agent（专业团队）

### 定义

**Agent = 完整的 AI 实体**，拥有：
- 独立的 System Prompt（团队手册）
- 特定的权限配置（能做什么）
- 自己的工作模式（主代理/子代理）
- 独立的上下文（记忆隔离）

### 类比

Agent 就像公司里的**完整团队**：
- 有自己的**团队手册**（System Prompt）
- 有**门禁权限**（Permission Rules）
- 在**独立办公室**工作（Session 隔离）
- 通过**派遣单**联系（Task Tool）

### OpenCode 的 Agent 类型

| Agent | 类型 | 权限特点 | 用途 |
|-------|------|---------|------|
| **build** | Primary | 全能（edit/bash/read 都允许） | 默认开发代理 |
| **plan** | Primary | 只读（edit 禁止） | 规划模式，不修改代码 |
| **explore** | Subagent | 只读（edit/write 禁止） | 代码库探索专家 |
| **general** | Subagent | 无 todo（todowrite 禁止） | 并行研究任务 |
| **title** | Hidden | 无工具权限 | 自动生成对话标题 |
| **summary** | Hidden | 无工具权限 | 生成对话摘要 |
| **compaction** | Hidden | 无工具权限 | 上下文压缩 |

### 何时使用 Agent

```
✅ 使用 Agent 的场景：

1. 需要完整独立的 AI 实例
   "帮我探索这个大型代码库的架构"
   → 派遣 explore 子代理

2. 需要特定的权限约束
   "只帮我规划，不要改代码"
   → 切换到 plan 代理

3. 任务复杂到需要独立的上下文
   "同时分析前端和后端代码"
   → 并行派遣多个子代理

4. 需要后台自动处理
   "给这个对话起个标题"
   → title 代理自动运行
```

### 代码示例

```typescript
// agent.ts - 定义一个探索型子代理
explore: {
  name: "explore",
  mode: "subagent",
  permission: PermissionNext.merge(defaults, PermissionNext.fromConfig({
    "*": "deny",        // 默认禁止所有
    grep: "allow",      // 只允许搜索
    glob: "allow",
    read: "allow",
    bash: "allow",
    // edit/write 被明确禁止！
  })),
  description: "Fast agent specialized for exploring codebases...",
  prompt: PROMPT_EXPLORE,  // 加载 explore.txt
}
```

---

## 2️⃣ Skill（专家手册）

### 定义

**Skill = 专业化的指令集 + 资源包**，包括：
- `SKILL.md`：详细的专业指南
- 附属资源：脚本、模板、参考文档
- 通过 Skill Tool 动态加载到当前 Agent

### 类比

Skill 就像**专家手册**：
- 项目经理（主 Agent）平时不带所有手册
- 遇到特定任务时（如"做 PPT"），**临时加载**对应手册
- 手册加载后，项目经理获得该领域专业知识
- **不会创建新团队**，只是给现有团队增加能力

### Skill 目录结构

```
~/.agents/skills/pptx/
├── SKILL.md              # 核心指南（必须）
├── LICENSE.txt           # 许可证
├── ooxml/
│   └── scripts/
│       ├── unpack.py     # 解包脚本
│       └── pack.py       # 打包脚本
└── templates/
    └── template.pptx     # 示例模板
```

### SKILL.md 示例

```markdown
---
name: pptx
description: "Presentation creation, editing, and analysis..."
license: Proprietary
---

# PPTX creation, editing, and analysis

## Overview
A user may ask you to create, edit, or analyze the contents of a .pptx file...

## Reading and analyzing content
### Text extraction
If you just need to read the text contents...

```bash
python -m markitdown path-to-file.pptx
```

### Raw XML access
You need raw XML access for: comments, speaker notes...
```

### 何时使用 Skill

```
✅ 使用 Skill 的场景：

1. 特定领域的专业知识
   "帮我做一个 PPT"
   → 加载 pptx skill

2. 需要配套资源（脚本、模板）
   "分析这个 Excel 数据"
   → 加载 xlsx skill（含处理脚本）

3. 复杂任务的标准化流程
   "测试这个网页应用"
   → 加载 webapp-testing skill

4. 领域特定的最佳实践
   "用 Python 做数据分析"
   → 加载 data-analysis skill

❌ 不使用 Skill 的场景：

1. 通用编程任务（用主 Agent 即可）
2. 单次简单操作（直接用 Tool）
3. 需要完全隔离上下文（用 Agent）
```

### Skill 加载流程

```
用户: "帮我做个 PPT"
        ↓
主 Agent 识别到需要 pptx 专业知识
        ↓
调用 Skill Tool: skill({ name: "pptx" })
        ↓
系统查找 ~/.agents/skills/pptx/SKILL.md
        ↓
加载 SKILL.md 内容 + 相关资源文件
        ↓
内容注入当前对话上下文
        ↓
主 Agent 现在拥有 PPT 制作能力
```

### 代码实现

```typescript
// skill.ts - Skill 加载工具
export const SkillTool = Tool.define("skill", async (ctx) => {
  return {
    description: "Load a specialized skill that provides domain-specific instructions...",
    parameters: z.object({
      name: z.string().describe("The name of the skill from available_skills"),
    }),
    async execute(params, ctx) {
      const skill = await Skill.get(params.name)
      
      return {
        output: [
          `<skill_content name="${skill.name}">`,
          skill.content,  // SKILL.md 内容
          "<skill_files>",
          files,          // 相关资源文件
          "</skill_files>",
          "</skill_content>",
        ].join("\n"),
      }
    },
  }
})
```

---

## 3️⃣ Tool（工具/能力）

### 定义

**Tool = 可执行的函数/能力**，包括：
- 明确的输入参数定义（Zod Schema）
- 执行逻辑
- 返回结果
- 权限检查

### 类比

Tool 就像**工具/设备**：
- Read Tool = 文件阅读器
- Edit Tool = 文本编辑器
- Bash Tool = 命令行终端
- Task Tool = 团队派遣系统
- Skill Tool = 手册加载器

**关键**：Tool 是 Agent 的**能力延伸**，不是独立实体。

### Tool 类型

| Tool | 用途 | 参数示例 |
|------|------|---------|
| **Read** | 读取文件 | `{ filePath: string }` |
| **Glob** | 文件匹配 | `{ pattern: string }` |
| **Grep** | 文本搜索 | `{ pattern: string, path?: string }` |
| **Edit** | 编辑文件 | `{ filePath: string, oldString: string, newString: string }` |
| **Write** | 写入文件 | `{ filePath: string, content: string }` |
| **Bash** | 执行命令 | `{ command: string, description?: string }` |
| **Task** | 派遣子代理 | `{ description: string, prompt: string, subagent_type: string }` |
| **TodoWrite** | 管理任务 | `{ todos: Array<{content, status, priority}> }` |
| **WebFetch** | 抓取网页 | `{ url: string }` |
| **Skill** | 加载技能 | `{ name: string }` |

### 何时创建新 Tool

```
✅ 创建新 Tool 的场景：

1. 需要执行特定代码逻辑
   "需要与特定 API 交互"
   → 创建 API Tool

2. 需要封装复杂操作
   "需要打包和解包 PPTX 文件"
   → 创建 Pack/Unpack Tool

3. 需要特定权限控制
   "这个操作需要用户确认"
   → 创建带 ask() 的 Tool

4. 需要复用的功能
   "多处需要读取配置文件"
   → 创建 ReadConfig Tool

❌ 不创建 Tool 的场景：

1. 只是给 AI 增加知识（用 Skill）
2. 需要完整独立上下文（用 Agent）
3. 调用外部已有服务（用 MCP）
```

### Tool 结构

```typescript
export const MyTool = Tool.define("mytool", {
  description: "Clear description of what this tool does...",
  parameters: z.object({
    param1: z.string().describe("Description of param1"),
    param2: z.number().optional(),
  }),
  async execute(params, ctx) {
    // 1. 权限检查
    await ctx.ask({ permission: "mytool", patterns: ["*"] })
    
    // 2. 执行逻辑
    const result = await doSomething(params)
    
    // 3. 返回结果
    return {
      title: "操作标题",
      output: "操作结果（会被截断 if 太长）",
      metadata: { /* 元数据 */ },
    }
  },
})
```

---

## 4️⃣ MCP（外部服务协议）

### 定义

**MCP = Model Context Protocol**，是 Anthropic 提出的开放标准：
- 连接外部服务和数据源
- 标准化的工具/资源接口
- 支持 OAuth 认证
- 独立于 OpenCode 运行

### 类比

MCP 就像**外部服务商 API**：
- 数据库服务商（PostgreSQL MCP）
- 搜索服务商（Exa/Brave MCP）
- 企业内网服务（内部 API MCP）
- **不在公司内部**，通过协议对接

### MCP vs Tool 的核心区别

| 特性 | Tool | MCP |
|------|------|-----|
| **位置** | OpenCode 内部 | 外部服务 |
| **部署** | 随 OpenCode 一起 | 独立运行 |
| **通信** | 直接函数调用 | HTTP/SSE/Stdio |
| **认证** | OpenCode 内部权限 | OAuth/独立认证 |
| **发现** | 启动时加载 | 动态发现 |
| **示例** | Read/Glob/Bash | 数据库/搜索/内部 API |

### MCP 配置示例

```json
{
  "mcp": {
    "my-database": {
      "type": "remote",
      "url": "https://mcp.example.com/database",
      "oauth": {
        "client_id": "xxx",
        "authorization_url": "https://auth.example.com/authorize"
      }
    },
    "local-search": {
      "type": "stdio",
      "command": "python -m search_mcp_server",
      "env": { "API_KEY": "xxx" }
    }
  }
}
```

### 何时使用 MCP

```
✅ 使用 MCP 的场景：

1. 连接外部数据源
   "查询公司销售数据库"
   → 使用 PostgreSQL MCP Server

2. 使用外部搜索服务
   "搜索最新的技术文章"
   → 使用 Exa/Brave MCP Server

3. 访问企业内网服务
   "查一下 JIRA 上的任务"
   → 使用内部 JIRA MCP Server

4. 需要独立部署维护的服务
   "需要专门的图像识别服务"
   → 使用图像识别 MCP Server

❌ 不使用 MCP 的场景：

1. 功能简单可以直接写 Tool
2. 不需要外部网络访问
3. 需要紧密集成 OpenCode 内部状态
```

### MCP 架构

```
┌─────────────────┐         HTTP/SSE/Stdio         ┌─────────────────┐
│                 │ ◄──────────────────────────────► │                 │
│   OpenCode      │                                 │   MCP Server    │
│   (MCP Client)  │                                 │   (外部服务)     │
│                 │  1. 发现工具列表                  │                 │
│                 │  2. 调用工具                      │                 │
│                 │  3. 获取资源                      │                 │
│                 │                                 │                 │
└─────────────────┘                                 └─────────────────┘
        │                                                    │
        │                                                    │
        ▼                                                    ▼
  ┌──────────────┐                                  ┌──────────────┐
  │  Tools       │                                  │  数据库      │
  │  Resources   │                                  │  搜索引擎    │
  │  Prompts     │                                  │  内部 API    │
  └──────────────┘                                  └──────────────┘
```

---

## 🎯 决策树：我该用什么？

```
面对一个新需求，按以下流程决策：

                    ┌──────────────────┐
                    │   新需求来了！    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ 需要独立上下文？  │
                    │ (隔离、并行、特殊权限)│
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │ YES                         │ NO
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │   使用 AGENT    │           │ 需要外部服务？   │
    │  (派遣子代理)    │           │ (数据库/搜索/API)│
    └─────────────────┘           └────────┬────────┘
                                           │
                            ┌──────────────┴──────────────┐
                            │ YES                         │ NO
                            ▼                             ▼
                  ┌─────────────────┐           ┌─────────────────┐
                  │   使用 MCP      │           │ 只是增加知识？   │
                  │ (外部服务协议)   │           │ (无新执行能力)   │
                  └─────────────────┘           └────────┬────────┘
                                                         │
                                          ┌──────────────┴──────────────┐
                                          │ YES                         │ NO
                                          ▼                             ▼
                                ┌─────────────────┐           ┌─────────────────┐
                                │   使用 SKILL    │           │   使用 TOOL     │
                                │ (专家手册+资源)  │           │ (新执行能力)    │
                                └─────────────────┘           └─────────────────┘
```

---

## 📊 四者对比表

| 维度 | Agent | Skill | Tool | MCP |
|------|-------|-------|------|-----|
| **本质** | 完整 AI 实体 | 专业知识包 | 执行函数 | 外部服务接口 |
| **上下文** | 完全独立 | 注入当前上下文 | 当前上下文 | 跨服务共享 |
| **System Prompt** | ✅ 有独立 Prompt | ❌ 无 | ❌ 无 | ❌ 无 |
| **权限控制** | ✅ 完整权限系统 | ⚠️ 通过 Skill Tool | ✅ 独立权限 | ✅ OAuth |
| **资源文件** | ❌ 无 | ✅ 可以有脚本/模板 | ❌ 无 | ✅ 外部资源 |
| **启动成本** | 高（新 Session） | 低（动态加载） | 低（直接调用） | 中（连接建立）|
| **适用场景** | 复杂独立任务 | 领域专业知识 | 原子操作 | 外部系统集成 |

---

## 💡 实际案例

### 场景：开发一个支持 PPT 生成的 AI 助手

**方案 A：只用 Tool（简陋版）**
```typescript
// 创建 GeneratePPT Tool
// 问题：AI 不懂 PPT 结构、设计原则、如何操作 XML
// 结果：生成的 PPT 质量差
```

**方案 B：使用 Skill（推荐版）**
```
1. 创建 pptx Skill
   ├── SKILL.md（PPT 制作指南）
   ├── scripts/unpack.py（解包脚本）
   └── scripts/pack.py（打包脚本）

2. 用户说"做个 PPT"
   → 主 Agent 调用 skill({ name: "pptx" })
   → 加载专业知识
   → 使用 bash/edit 等现有工具操作文件
   
3. 结果：高质量 PPT，充分利用 AI 的通用能力 + 专业知识
```

**方案 C：使用 Agent（过度设计版）**
```
创建 pptx-agent
问题：
- 需要独立的 Session（启动慢）
- 仍然需要与主 Agent 通信
- 无法直接复用主 Agent 的文件操作能力
结果：复杂且低效
```

**方案 D：使用 MCP（服务化版）**
```
如果：
- PPT 生成需要专门的服务器（如高性能渲染）
- 需要连接 PPT 模板数据库
- 团队其他产品也需要 PPT 功能

则：创建 PPT MCP Server
好处：
- 服务独立部署维护
- 多客户端共享
- 专业的资源管理
```

---

## 🏆 最佳实践

### 1. 从 Tool 开始

> "先做成 Tool，只有当 Tool 不够用时，才考虑 Skill 或 Agent"

大多数需求都可以先用 Tool 实现，只有当发现：
- 需要大量专业知识指导
- 需要配套资源（脚本、模板）

才升级为 Skill。

### 2. Skill 优于 Agent

> "能用 Skill 解决的，不要用 Agent"

Skill 的优势：
- 加载快（不用创建新 Session）
- 资源省（复用主 Agent 上下文）
- 更灵活（可以和主 Agent 的工具组合）

### 3. Agent 用于真正的隔离

只有当需要：
- **权限隔离**（如只读探索）
- **并行执行**（同时处理多个独立任务）
- **上下文隔离**（防止相互干扰）

才使用 Agent。

### 4. MCP 用于外部集成

MCP 是"最后一招"：
- 连接已有外部服务
- 需要独立运维的服务
- 跨产品复用的能力

---

## 📝 一句话总结

> **Agent 是派团队，Skill 是请专家，Tool 是用工具，MCP 是叫外卖。选择合适的抽象层级，既不过度设计（什么都用 Agent），也不能力不足（该用 Skill 却用 Tool），是设计优秀 AI 系统的关键！** 🎯

---

*分析完成时间：2026-03-16*
*分析者：Kimi Code*
