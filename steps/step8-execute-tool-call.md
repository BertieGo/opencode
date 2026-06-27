# Step 8: 执行工具调用（Bash）—— AI 的"行动执行"

> **一句话总结**：当 AI 决定调用 bash 工具时，系统会解析命令、检查权限、执行命令，并将结果返回给 AI。

---

## 🎬 场景回顾

前七步完成了：
1. ✅ **Step 1**：用户消息已打包
2. ✅ **Step 2**：确定使用 build Agent
3. ✅ **Step 3**：Agent 配置绑定到会话
4. ✅ **Step 4**：检查并压缩会话状态
5. ✅ **Step 5**：组装 System Prompt
6. ✅ **Step 6**：组装可用工具列表
7. ✅ **Step 7**：调用 LLM，AI 决定调用 bash

现在 AI 输出了：
```json
{
  "tool": "bash",
  "input": {
    "command": "bun test",
    "description": "运行测试查看错误"
  }
}
```

系统要**实际执行这个命令**了！

---

## 🔧 工具执行流程图

```
AI 调用 bash 工具
       │
       ▼
┌─────────────────┐
│  1. 解析参数     │
│  验证 schema    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. 安全检查     │
│  解析命令 AST   │
│  识别危险操作   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. 权限检查     │
│  bash: ask     │
│  external_dir: ask │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
  允许       拒绝
    │         │
    ▼         ▼
┌─────────────────┐
│  4. 执行命令     │
│  spawn 子进程   │
│  捕获输出      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. 返回结果     │
│  output        │
│  exit code     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  6. 更新状态     │
│  tool-result   │
└─────────────────┘
```

---

## 📋 Tool 接口定义

所有工具都遵循统一的接口：

```typescript
// packages/opencode/src/tool/tool.ts

export namespace Tool {
  export interface Context {
    sessionID: SessionID      // 会话 ID
    messageID: MessageID      // 消息 ID
    agent: string             // Agent 名称
    abort: AbortSignal        // 取消信号
    callID?: string           // 调用 ID
    extra?: { [key: string]: any }
    messages: MessageV2.WithParts[]  // 历史消息
    
    // 更新元数据（实时显示执行状态）
    metadata(input: { title?: string; metadata?: M }): void
    
    // 询问权限
    ask(input: PermissionNext.Request): Promise<void>
  }

  export interface Info {
    id: string
    init: (ctx?: InitContext) => Promise<{
      description: string                    // 工具描述
      parameters: z.ZodType                  // 参数 schema
      execute(args, ctx: Context): Promise<{ // 执行函数
        title: string
        metadata: M
        output: string
      }>
    }>
  }
}
```

---

## 🚀 Bash 工具详解

### 定义与初始化

```typescript
// packages/opencode/src/tool/bash.ts 第 55-77 行

export const BashTool = Tool.define("bash", async () => {
  const shell = Shell.acceptable()  // 检测可用的 shell
  
  return {
    // 动态生成描述（替换模板变量）
    description: DESCRIPTION
      .replaceAll("${directory}", Instance.directory)
      .replaceAll("${maxLines}", String(Truncate.MAX_LINES))
      .replaceAll("${maxBytes}", String(Truncate.MAX_BYTES)),
    
    // 参数定义
    parameters: z.object({
      command: z.string().describe("The command to execute"),
      
      timeout: z.number()
        .describe("Optional timeout in milliseconds")
        .optional(),
      
      workdir: z.string()
        .describe(`Working directory. Defaults to ${Instance.directory}`)
        .optional(),
      
      description: z.string()
        .describe("Clear description of what this command does in 5-10 words"),
    }),
    
    // 执行函数
    async execute(params, ctx) {
      // ... 执行逻辑
    }
  }
})
```

### 执行流程

```typescript
async execute(params, ctx) {
  // 1. 确定工作目录
  const cwd = params.workdir || Instance.directory
  
  // 2. 确定超时时间
  const timeout = params.timeout ?? DEFAULT_TIMEOUT  // 默认 2 分钟
  
  // 3. 解析命令 AST
  const tree = await parser().then((p) => p.parse(params.command))
  
  // 4. 安全检查 - 分析命令
  const directories = new Set<string>()
  const patterns = new Set<string>()
  const always = new Set<string>()
  
  for (const node of tree.rootNode.descendantsOfType("command")) {
    // 提取命令名和参数
    const command = []
    for (let i = 0; i < node.childCount; i++) {
      const child = node.child(i)
      if (["command_name", "word", "string", "raw_string", "concatenation"]
          .includes(child.type)) {
        command.push(child.text)
      }
    }
    
    // 检测访问外部目录的命令
    if (["cd", "rm", "cp", "mv", "mkdir", "touch", "chmod", "chown", "cat"]
        .includes(command[0])) {
      for (const arg of command.slice(1)) {
        const resolved = await fs.realpath(path.resolve(cwd, arg)).catch(() => "")
        if (resolved && !Instance.containsPath(resolved)) {
          directories.add(path.dirname(resolved))
        }
      }
    }
    
    // 收集命令模式用于权限检查
    if (command.length && command[0] !== "cd") {
      patterns.add(commandText)
      always.add(BashArity.prefix(command).join(" ") + " *")
    }
  }
```

---

## 🛡️ 权限检查机制

### 两层权限检查

```typescript
// 第一层：外部目录访问检查
if (directories.size > 0) {
  const globs = Array.from(directories).map((dir) => {
    return path.join(dir, "*")
  })
  
  await ctx.ask({
    permission: "external_directory",
    patterns: globs,
    always: globs,
    metadata: {},
  })
}

// 第二层：bash 命令权限检查
if (patterns.size > 0) {
  await ctx.ask({
    permission: "bash",
    patterns: Array.from(patterns),
    always: Array.from(always),
    metadata: {},
  })
}
```

### 权限配置示例

```yaml
# ~/.opencode/opencode.yml

permission:
  bash:
    "git *": "allow"        # 允许所有 git 命令
    "npm *": "allow"        # 允许所有 npm 命令
    "rm -rf /": "deny"      # 禁止危险命令
    "*": "ask"              # 其他命令询问
  
  external_directory:
    "/tmp/*": "allow"       # 允许访问 /tmp
    "*": "ask"              # 其他外部目录询问
```

---

## ⚡ 命令执行

### 创建子进程

```typescript
// 触发插件获取环境变量
const shellEnv = await Plugin.trigger(
  "shell.env",
  { cwd, sessionID: ctx.sessionID, callID: ctx.callID },
  { env: {} },
)

// 创建子进程
const proc = spawn(params.command, {
  shell,           // 使用检测到的 shell
  cwd,             // 工作目录
  env: {
    ...process.env,
    ...shellEnv.env,  // 合并插件提供的环境变量
  },
  stdio: ["ignore", "pipe", "pipe"],  // 忽略 stdin，捕获 stdout/stderr
  detached: process.platform !== "win32",
  windowsHide: process.platform === "win32",
})
```

### 实时捕获输出

```typescript
let output = ""

// 初始化元数据（实时显示）
ctx.metadata({
  metadata: {
    output: "",
    description: params.description,
  },
})

const append = (chunk: Buffer) => {
  output += chunk.toString()
  
  // 实时更新元数据（UI 可以显示进度）
  ctx.metadata({
    metadata: {
      output: output.length > MAX_METADATA_LENGTH 
        ? output.slice(0, MAX_METADATA_LENGTH) + "\n\n..." 
        : output,
      description: params.description,
    },
  })
}

proc.stdout?.on("data", append)
proc.stderr?.on("data", append)
```

---

## ⏱️ 超时和取消机制

### 超时处理

```typescript
let timedOut = false
let aborted = false
let exited = false

// 超时定时器
const timeoutTimer = setTimeout(() => {
  timedOut = true
  void kill()  // 终止进程
}, timeout + 100)
```

### 取消处理

```typescript
// 如果已经取消了，立即终止
if (ctx.abort.aborted) {
  aborted = true
  await kill()
}

// 监听取消事件
const abortHandler = () => {
  aborted = true
  void kill()
}
ctx.abort.addEventListener("abort", abortHandler, { once: true })
```

### 进程终止

```typescript
const kill = () => Shell.killTree(proc, { exited: () => exited })
// 使用 killTree 确保子进程也被终止
```

### 等待进程结束

```typescript
await new Promise<void>((resolve, reject) => {
  const cleanup = () => {
    clearTimeout(timeoutTimer)
    ctx.abort.removeEventListener("abort", abortHandler)
  }

  proc.once("exit", () => {
    exited = true
    cleanup()
    resolve()
  })

  proc.once("error", (error) => {
    exited = true
    cleanup()
    reject(error)
  })
})
```

---

## 📤 返回结果

### 添加元数据

```typescript
const resultMetadata: string[] = []

if (timedOut) {
  resultMetadata.push(`bash tool terminated command after exceeding timeout ${timeout} ms`)
}

if (aborted) {
  resultMetadata.push("User aborted the command")
}

if (resultMetadata.length > 0) {
  output += "\n\n<bash_metadata>\n" + resultMetadata.join("\n") + "\n</bash_metadata>"
}
```

### 返回格式

```typescript
return {
  title: params.description,           // 命令描述
  metadata: {
    output: output.slice(0, MAX_METADATA_LENGTH),  // 截断的输
    exit: proc.exitCode,               // 退出码
    description: params.description,
  },
  output,                              // 完整输出
}
```

---

## 🎯 完整执行示例

### 场景：运行测试

```
User: 运行测试看看有没有错误

AI 思考：
"用户想运行测试，我应该调用 bash 工具执行 bun test"

AI 输出：
{
  "tool": "bash",
  "input": {
    "command": "bun test",
    "description": "运行测试套件"
  }
}

系统处理：
1. 解析参数 ✓
2. AST 解析：命令是 "bun test"
3. 安全检查：bun 不在危险命令列表
4. 权限检查：
   - 无外部目录访问
   - bash 权限："bun *" = "allow" ✓
5. 执行命令：
   - spawn("bun test", { cwd: "/project", ... })
   - 实时捕获输出
6. 命令完成：
   - exit code: 1 (有测试失败)
   - 输出：错误堆栈...
7. 返回结果给 AI

AI 看到结果：
"测试失败了，错误是...让我查看具体文件"
```

---

## 🛡️ 安全机制总结

| 安全层 | 机制 | 目的 |
|--------|------|------|
| Schema 验证 | Zod 校验 | 确保参数格式正确 |
| AST 解析 | tree-sitter-bash | 理解命令结构 |
| 危险命令检测 | 硬编码列表 | 识别 rm/cp/mv 等 |
| 外部目录检测 | 路径解析 | 防止访问工作目录外 |
| 权限系统 | ask/allow/deny | 用户控制 |
| 超时机制 | setTimeout | 防止无限挂起 |
| 取消机制 | AbortSignal | 用户可随时停止 |

---

## 🎭 形象比喻：实验室实验

| 现实场景 | OpenCode Step 8 |
|---------|----------------|
| 研究员提出实验方案 | AI 决定调用 bash |
| 方案审核 | Schema 验证 |
| 安全评估 | AST 解析 + 危险命令检测 |
| 申请实验许可 | ctx.ask() 权限检查 |
| 准备实验环境 | spawn 子进程 |
| 实时观察实验 | stdout/stderr 捕获 |
| 紧急停止按钮 | AbortSignal 取消 |
| 自动保护（超时）| setTimeout 超时 |
| 实验记录 | 返回 output + metadata |

**完整场景**：

> 研究员（AI）想做实验（运行命令）：
> 
> 1. **提交方案**："我要运行 bun test"
> 2. **方案审核**：格式正确吗？参数合法吗？（Zod 校验）
> 3. **安全评估**：这个实验安全吗？（AST 解析）
>    - "bun" 不是危险命令 ✓
>    - 不涉及外部目录 ✓
> 4. **申请许可**：向实验室主管（用户）申请
>    - "允许 bun 命令吗？" → "允许" ✓
> 5. **开始实验**：在实验室（工作目录）执行
> 6. **实时观察**：记录实验现象（输出）
> 7. **实验结束**：整理实验报告（返回结果）

---

## 🔍 关键代码文件速查

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| Tool 接口定义 | `packages/opencode/src/tool/tool.ts` | 1-90 |
| Bash 工具 | `packages/opencode/src/tool/bash.ts` | 55-270 |
| 命令解析 | `packages/opencode/src/tool/bash.ts` | 84-137 |
| 权限检查 | `packages/opencode/src/tool/bash.ts` | 139-160 |
| 进程执行 | `packages/opencode/src/tool/bash.ts` | 167-243 |
| 结果返回 | `packages/opencode/src/tool/bash.ts` | 259-267 |
| 工具描述 | `packages/opencode/src/tool/bash.txt` | 全文 |

---

## 🚀 下一步

完成 Step 8 后：
1. ✅ 命令已执行
2. ✅ 输出已捕获
3. ✅ 结果已返回

系统会把结果作为 `tool-result` 事件返回给主循环，然后进入 **Step 9: 更新会话状态**。

准备好进入 **Step 9** 了吗？
