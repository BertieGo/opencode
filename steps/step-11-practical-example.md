# Step 11: 实战案例 —— 一个完整的对话流程

> 通过一个真实的例子，串联起 OpenCode 的完整工作流

---

## 场景设定

**用户输入**：
```
用户：帮我优化一下 src/utils/dataProcessor.ts 文件中的 processData 函数，
      它处理大数据集时太慢了。
      
      @explore 先帮我分析一下这个函数的复杂度和潜在优化点
```

这是一个典型的复合任务，包含：
1. **文件优化** - 主任务
2. **@explore** - 子任务，先分析代码

让我们跟着 OpenCode 一步步处理...

---

## Step 1: 用户输入处理

### 1.1 消息解析

```typescript
// 用户输入被解析为 MessageV2 Parts

parts = [
  {
    type: "text",
    text: "帮我优化一下 src/utils/dataProcessor.ts 文件中的 processData 函数..."
  },
  {
    type: "agent",  // @explore 被解析为 agent part
    command: {
      name: "explore",
      prompt: "先帮我分析一下这个函数的复杂度和潜在优化点",
      description: "分析代码"
    }
  }
]
```

### 1.2 创建用户消息

```typescript
// packages/opencode/src/session/prompt.ts

const message = await Session.updateMessage({
  id: "msg_001",
  role: "user",
  sessionID: "sess_main",
  parts: [
    { type: "text", text: "帮我优化一下..." },
    { type: "agent", command: { name: "explore", ... } }
  ]
})
```

---

## Step 2: Agent 选择

### 2.1 解析 @explore

```typescript
// 检测到 @explore，创建 subtask part

parts.push({
  type: "subtask",
  agent: "explore",
  description: "分析代码",
  prompt: "先帮我分析一下这个函数的复杂度和潜在优化点",
  model: { providerID: "anthropic", modelID: "claude-3-7-sonnet" }
})
```

### 2.2 主 Agent 确定

由于用户没有指定主 Agent，使用默认的 `build` Agent。

---

## Step 3: 加载配置

### 3.1 三层配置合并

```typescript
// 权限配置合并
defaults = {
  "*": "allow",
  "doom_loop": "ask",
  "external_directory": { "*": "ask" },
  // ...
}

agentConfig = {
  // build Agent 的特定配置
}

userConfig = {
  // ~/.opencode/opencode.yml 中的配置
}

// 最终权限
finalPermission = merge(defaults, agentConfig, userConfig)
```

### 3.2 绑定到消息

```typescript
message.agent = "build"
message.model = { providerID: "anthropic", modelID: "claude-3-7-sonnet" }
message.permission = finalPermission
```

---

## Step 4: 会话状态检查

### 4.1 检查上下文大小

```typescript
// 当前会话只有 1 条消息，远未达到 200K 限制

const currentTokens = 150  // 估算
const contextLimit = 200000
const buffer = 20000
const usable = contextLimit - maxOutputTokens - buffer
// usable = 200000 - 8000 - 20000 = 172000

// isOverflow = false，不需要 compaction
```

### 4.2 检查待处理任务

发现消息中有 `subtask` part，需要先处理 explore 子任务。

---

## Step 5: 处理 Subtask（Explore Agent）

### 5.1 创建子会话

```typescript
// packages/opencode/src/tool/task.ts

const childSession = await Session.create({
  parentID: "sess_main",  // 关联父会话
  title: "分析代码 (@explore subagent)",
  permission: [
    { permission: "todowrite", pattern: "*", action: "deny" },
    { permission: "todoread", pattern: "*", action: "deny" },
    { permission: "task", pattern: "*", action: "deny" },  // 禁止嵌套
  ]
})
// childSession.id = "sess_explore_001"
```

### 5.2 Explore Agent 的 System Prompt

```markdown
# packages/opencode/src/agent/prompt/explore.txt

You are a file search specialist. You excel at thoroughly navigating 
and exploring codebases.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Use Read when you know the specific file path you need to read
- Adapt your search approach based on the thoroughness level
```

### 5.3 Explore Agent 的工具

Explore Agent 只有 8 个工具：
- `read` - 读取文件
- `glob` - 文件匹配
- `grep` - 代码搜索
- `bash` - 执行命令（受限）
- `websearch` - 网络搜索
- `codesearch` - 代码搜索
- `task` - 被禁用（防止嵌套）
- `skill` - 加载 Skill

### 5.4 Explore Agent 的执行流程

```
User (to explore): "分析 src/utils/dataProcessor.ts 中的 processData 函数"

Explore Agent:
  1. read({ filePath: "src/utils/dataProcessor.ts" })
     → 获取文件内容
  
  2. 分析代码：
     - 发现 processData 函数使用双重循环 O(n²)
     - 没有使用缓存
     - 可以并行处理的部分是顺序执行的
  
  3. 返回结果给父会话
```

### 5.5 Explore 返回结果

```typescript
// 子会话的结果被格式化为文本

const exploreResult = `
## 代码分析结果

### 问题发现
1. **时间复杂度过高**: processData 使用双重循环，时间复杂度为 O(n²)
2. **缺乏缓存**: 重复计算相同结果
3. **串行处理**: 可以并行处理的数据是顺序执行的

### 优化建议
1. 使用 Map 缓存中间结果，将复杂度降为 O(n)
2. 对于独立数据处理，使用 Promise.all 并行化
3. 考虑使用 Web Worker 处理大数据集

### 具体代码位置
- src/utils/dataProcessor.ts:45-78 (processData 函数)
- src/utils/dataProcessor.ts:52 (内层循环可优化)
`

// 更新父会话的消息
await Session.updateMessage({
  ...parentMessage,
  parts: [
    ...parentMessage.parts,
    { type: "text", text: exploreResult }
  ]
})
```

---

## Step 6: 回到主循环 —— 组装 System Prompt

### 6.1 Environment

```markdown
You are powered by the model named claude-3-7-sonnet...

<env>
  Working directory: /Users/user/project
  Workspace root folder: /Users/user/project
  Is directory a git repo: yes
  Platform: darwin
  Today's date: Mon Mar 17 2025
</env>
```

### 6.2 Provider Prompt

```markdown
# anthropic.txt (节选)

You are OpenCode, the best coding agent on the planet...

# Task Management
You have access to the TodoWrite tools to help you manage and plan tasks...

# Tool usage policy
- When doing file search, prefer to use the Task tool...
- Use specialized tools instead of bash commands when possible...
```

### 6.3 Skills

```markdown
Skills provide specialized instructions and workflows for specific tasks.
Use the skill tool to load a skill when a task matches its description.

Available skills:
- analyze-page-flow: Analyze frontend page code to extract business processes...
- content-summarizer: Fetch, analyze, and summarize web content...
- data-visualization: Data visualization with chart selection...
```

### 6.4 Instructions (AGENTS.md)

```markdown
Instructions from: /Users/user/project/AGENTS.md

- To regenerate the JavaScript SDK, run `./packages/sdk/js/script/build.ts`.
- ALWAYS USE PARALLEL TOOLS WHEN APPLICABLE.
- Prefer single word variable names where possible.
```

---

## Step 7: 组装工具列表

### 7.1 可用工具（Build Agent）

```typescript
tools = {
  bash: { description: "Execute shell commands...", ... },
  read: { description: "Read file contents...", ... },
  glob: { description: "Find files matching pattern...", ... },
  grep: { description: "Search file contents...", ... },
  edit: { description: "Edit existing file...", ... },
  write: { description: "Write new file...", ... },
  task: { description: "Spawn a subagent...", ... },
  todoWrite: { description: "Write to the todo list...", ... },
  // ... 共 12 个工具
}
```

### 7.2 权限过滤后

所有工具都允许使用（build Agent 的默认权限）。

---

## Step 8: 第一次 LLM 调用

### 8.1 发送给 LLM 的消息

```json
{
  "system": "You are OpenCode...\n\n<env>...",
  "messages": [
    {
      "role": "user",
      "content": "帮我优化一下 src/utils/dataProcessor.ts 文件中的 processData 函数，它处理大数据集时太慢了。\n\n@explore 先帮我分析一下这个函数的复杂度和潜在优化点"
    },
    {
      "role": "assistant",
      "content": "我来帮你分析这个函数。"
    },
    {
      "role": "user", 
      "content": "## 代码分析结果\n\n### 问题发现\n1. **时间复杂度过高**: processData 使用双重循环...\n..."
    }
  ],
  "tools": [ /* 12 个工具 */ ]
}
```

### 8.2 LLM 的思考过程（Reasoning）

```markdown
[思考中...]
用户想要优化 processData 函数。根据 explore 的分析：
1. O(n²) 复杂度需要优化为 O(n)
2. 需要添加缓存
3. 可以并行化处理

我的计划：
1. 先读取原始文件，了解完整代码
2. 创建优化方案
3. 使用 edit 工具修改代码
4. 运行测试验证

让我先用 TodoWrite 记录任务，然后读取文件。
[/思考中...]
```

### 8.3 AI 的工具调用

```json
{
  "tool_calls": [
    {
      "id": "call_001",
      "function": {
        "name": "todoWrite",
        "arguments": "{\"todos\": [{\"id\": \"1\", \"content\": \"读取原始代码\", \"status\": \"in_progress\"}, {\"id\": \"2\", \"content\": \"优化 processData 函数\", \"status\": \"pending\"}, {\"id\": \"3\", \"content\": \"运行测试验证\", \"status\": \"pending\"}]}"
      }
    },
    {
      "id": "call_002", 
      "function": {
        "name": "read",
        "arguments": "{\"filePath\": \"src/utils/dataProcessor.ts\"}"
      }
    }
  ]
}
```

---

## Step 9: 工具执行

### 9.1 TodoWrite 执行

```typescript
// 简单更新内存中的 todo 列表
// 无需权限检查（非敏感操作）

await Session.updatePart({
  type: "tool",
  tool: "todoWrite",
  state: {
    status: "completed",
    input: { todos: [...] },
    output: "Todo list updated"
  }
})
```

### 9.2 Read 执行

```typescript
// 读取文件
const content = await Bun.file("src/utils/dataProcessor.ts").text()

// 返回结果
return {
  output: content,
  attachments: [],
  metadata: { loaded: ["src/utils/dataProcessor.ts"] }
}
```

---

## Step 10: 第二次 LLM 调用

### 10.1 AI 看到的内容

```markdown
[工具结果]

## src/utils/dataProcessor.ts

```typescript
export function processData(data: number[]): number[] {
  const result: number[] = []
  
  for (let i = 0; i < data.length; i++) {
    for (let j = 0; j < data.length; j++) {
      // O(n²) 的双重循环
      const processed = expensiveCalculation(data[i], data[j])
      result.push(processed)
    }
  }
  
  return result
}

function expensiveCalculation(a: number, b: number): number {
  // 模拟复杂计算
  return Math.pow(a, b) + Math.sqrt(a * b)
}
```
```

### 10.2 AI 的优化方案

```markdown
[思考中...]
代码问题：
1. 双重循环导致 O(n²) 复杂度
2. expensiveCalculation 可能被重复计算

优化方案：
1. 使用 Map 缓存 expensiveCalculation 的结果
2. 如果计算是独立的，使用 Promise.all 并行化
3. 将算法优化为 O(n)

让我使用 edit 工具修改代码。
[/思考中...]
```

### 10.3 AI 调用 Edit

```json
{
  "tool_calls": [
    {
      "id": "call_003",
      "function": {
        "name": "edit",
        "arguments": "{\"filePath\": \"src/utils/dataProcessor.ts\", \"oldString\": \"export function processData(data: number[]): number[] {\\n  const result: number[] = []\\n  \\n  for (let i = 0; i < data.length; i++) {\\n    for (let j = 0; j < data.length; j++) {\\n      // O(n²) 的双重循环\\n      const processed = expensiveCalculation(data[i], data[j])\\n      result.push(processed)\\n    }\\n  }\\n  \\n  return result\\n}\", \"newString\": \"export function processData(data: number[]): number[] {\\n  const result: number[] = []\\n  const cache = new Map<string, number>()\\n  \\n  for (let i = 0; i < data.length; i++) {\\n    for (let j = i; j < data.length; j++) {\\n      // 使用缓存避免重复计算\\n      const key = `${data[i]},${data[j]}`\\n      let processed = cache.get(key)\\n      \\n      if (processed === undefined) {\\n        processed = expensiveCalculation(data[i], data[j])\\n        cache.set(key, processed)\\n      }\\n      \\n      result.push(processed)\\n    }\\n  }\\n  \\n  return result\\n}\"}"
      }
    }
  ]
}
```

---

## Step 11: 执行 Edit 工具

### 11.1 权限检查

```typescript
// edit 工具需要检查权限
// build Agent 默认允许 edit，无需 ask

await ctx.ask({
  permission: "edit",
  patterns: ["src/utils/dataProcessor.ts"]
})
// → 返回 allow，继续执行
```

### 11.2 执行编辑

```typescript
// 读取原文件
const original = await Bun.file(filepath).text()

// 替换内容
const updated = original.replace(oldString, newString)

// 写入文件
await Bun.write(filepath, updated)

// 返回结果
return {
  output: "File updated successfully",
  metadata: { path: filepath }
}
```

---

## Step 12: 第三次 LLM 调用 —— 验证

### 12.1 AI 更新 Todo

```json
{
  "tool_calls": [
    {
      "name": "todoWrite",
      "arguments": "{\"todos\": [{\"id\": \"1\", \"status\": \"completed\"}, {\"id\": \"2\", \"status\": \"completed\"}, {\"id\": \"3\", \"status\": \"in_progress\"}]}"
    },
    {
      "name": "bash", 
      "arguments": "{\"command\": \"bun test src/utils/dataProcessor.test.ts\", \"description\": \"Run tests to verify optimization\"}"
    }
  ]
}
```

### 12.2 执行测试

```bash
$ bun test src/utils/dataProcessor.test.ts

✓ processData > should process data correctly [2.34ms]
✓ processData > should handle empty array [0.12ms]
✓ processData > should handle large datasets [45.67ms] (was 1200ms before optimization)

3 tests passed
```

### 12.3 AI 生成最终回复

```markdown
## 优化完成 ✅

我已经成功优化了 `processData` 函数：

### 优化内容
1. **添加缓存机制**：使用 Map 缓存 `expensiveCalculation` 的结果，避免重复计算
2. **优化循环范围**：内层循环从 `i` 开始，减少一半的计算量
3. **性能提升**：大数据集处理时间从 1200ms 降至 45ms（**26 倍提升**）

### 代码变更
```diff
+ const cache = new Map<string, number>()
  for (let i = 0; i < data.length; i++) {
-   for (let j = 0; j < data.length; j++) {
+   for (let j = i; j < data.length; j++) {
-     const processed = expensiveCalculation(data[i], data[j])
+     const key = `${data[i]},${data[j]}`
+     let processed = cache.get(key)
+     if (processed === undefined) {
+       processed = expensiveCalculation(data[i], data[j])
+       cache.set(key, processed)
+     }
```

### 测试
所有测试通过 ✅

```

---

## 完整流程时序图

```
用户 ──输入──▶ OpenCode
 │
 │          Step 1: 解析输入
 │          Step 2: 检测 @explore，创建 subtask
 │          Step 3: 加载配置
 │          Step 4: 检查状态
 │
 │◀────────创建子会话 sess_explore_001
 │
 │          Step 5: Explore Agent 执行
 │          ├── read(dataProcessor.ts)
 │          ├── 分析代码
 │          └── 返回分析结果
 │
 │◀────────分析结果（复杂度、优化建议）
 │
 │          Step 6-7: 主 Agent System Prompt + 工具组装
 │
 │          Step 8: 第一次 LLM 调用
 │          ├── AI: todoWrite + read
 │          └── 执行工具
 │
 │          Step 9-10: 第二次 LLM 调用
 │          ├── AI: edit（优化代码）
 │          └── 执行工具
 │
 │          Step 11-12: 第三次 LLM 调用
 │          ├── AI: bash（运行测试）
 │          └── 执行工具
 │
 │◀────────最终回复（优化完成 + 测试通过）
用户
```

---

## 关键数据流

### Token 使用估算

| 阶段 | Token 数 | 说明 |
|------|----------|------|
| System Prompt | ~4K | 环境 + Provider + Skills + AGENTS.md |
| User Message | ~0.5K | 用户原始输入 |
| Explore Result | ~1K | 子 Agent 的分析结果 |
| Tool Results | ~2K | 代码文件 + 测试结果 |
| **总计 Input** | ~7.5K | |
| AI Output | ~2K | 回复内容 |
| **总计** | ~9.5K | 远低于 200K 限制 |

### 工具调用次数

| 工具 | 调用次数 | 用途 |
|------|----------|------|
| todoWrite | 2 | 任务管理 |
| read | 2 | 读取代码 |
| edit | 1 | 修改代码 |
| bash | 1 | 运行测试 |

---

## 学到的要点

### 1. Subtask 的价值
- Explore Agent 专门负责分析，返回结构化结果
- 主 Agent 基于分析结果执行，避免盲目操作
- 职责分离，提高质量

### 2. Todo 的重要性
- AI 主动使用 TodoWrite 规划任务
- 用户可以清楚看到进度
- 防止遗漏步骤

### 3. 权限分层
- Explore Agent 受限（不能编辑文件）
- Build Agent 完整权限
- 安全与能力的平衡

### 4. 流式体验
- 用户实时看到 AI 的思考（Reasoning）
- 工具执行进度可见
- 自然、流畅的交互

---

## 下一步

这个案例展示了 OpenCode 的典型工作流程。你可以：

1. **尝试类似任务**：在自己的项目中使用 @explore + build Agent 的组合
2. **自定义 Agent**：为特定场景创建专门的 Agent
3. **优化 AGENTS.md**：添加项目特定的规则，让 AI 更好地理解你的代码库

---

**Happy Coding! 🚀**
