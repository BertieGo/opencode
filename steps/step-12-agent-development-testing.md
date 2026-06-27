# Step 12: Agent 开发与测试指南

> 如何开发、测试和验证自定义 Agent

---

## 1. Agent 开发概述

### 1.1 Agent 配置格式

OpenCode 的 Agent 使用 **Markdown + YAML Frontmatter** 格式定义：

```markdown
---
name: my-agent
description: Use this agent when you need to...
mode: subagent
color: cyan
temperature: 0.3
tools:
  read: true
  write: true
  bash: ask
---

# My Agent

You are a specialized agent for...

## Guidelines

1. First, analyze the requirements
2. Then, create a plan
3. Finally, execute step by step
```

### 1.2 配置字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `name` | string | Agent 唯一标识 | `code-reviewer` |
| `description` | string | Agent 描述（用于匹配） | `Use this agent when...` |
| `mode` | string | Agent 模式 | `primary` / `subagent` / `hidden` |
| `color` | string | TUI 显示颜色 | `cyan` / `green` / `yellow` |
| `temperature` | number | 模型温度 | `0.1` - `1.0` |
| `tools` | object | 工具权限 | `{ read: true, edit: ask }` |
| `model` | string | 指定模型 | `anthropic/claude-3-7-sonnet` |
| `steps` | number | 最大步数限制 | `10` |

### 1.3 Agent 存储位置

```
~/.opencode/agents/              # 用户级 Agent
├── my-agent.md
└── code-reviewer.md

./.opencode/agents/              # 项目级 Agent（优先级更高）
├── project-specific-agent.md
└── team-coding-standard.md

packages/opencode/src/agent/prompt/  # 内置 Agent
├── explore.txt
├── compaction.txt
├── summary.txt
└── title.txt
```

---

## 2. Agent 开发流程

### 2.1 创建 Agent 文件

```bash
# 创建用户级 Agent 目录
mkdir -p ~/.opencode/agents

# 创建 Agent 文件
cat > ~/.opencode/agents/test-runner.md << 'EOF'
---
name: test-runner
description: |
  Use this agent when you need to run tests, analyze test failures, 
  and fix failing tests. This agent specializes in test-driven development.
mode: subagent
color: green
temperature: 0.1
tools:
  read: true
  glob: true
  grep: true
  bash: true
  todoWrite: true
---

# Test Runner Agent

You are a test automation expert. Your job is to:
1. Run test suites
2. Analyze failures
3. Fix failing tests
4. Improve test coverage

## Workflow

### Step 1: Discover Tests
- Use `glob` to find test files
- Common patterns: `**/*.test.ts`, `**/*.spec.ts`

### Step 2: Run Tests
- Use `bash` to execute test command
- Common commands: `bun test`, `npm test`, `pytest`

### Step 3: Analyze Failures
- Read failing test files
- Understand expected vs actual behavior
- Identify root cause

### Step 4: Fix Issues
- Edit test files if test is wrong
- Edit source files if implementation is wrong
- Run tests again to verify

## Best Practices

- Always run tests before making changes
- Fix one test at a time
- Keep tests isolated and deterministic
- Use descriptive test names
EOF
```

### 2.2 测试 Agent 配置

```bash
# 1. 验证 Agent 是否被识别
opencode debug agents

# 2. 查看 Agent 详情
opencode debug agent test-runner

# 3. 在 TUI 中按 Tab 切换 Agent，确认新 Agent 出现
```

### 2.3 使用新 Agent

```bash
# 方式 1: @ 提及
@test-runner run all tests in this project

# 方式 2: 直接启动
opencode test-runner

# 方式 3: 在 TUI 中 Tab 切换
```

---

## 3. Agent 测试策略

### 3.1 手动测试清单

创建 Agent 后，按照以下清单验证：

```markdown
## Agent 测试清单

### 基础功能
- [ ] Agent 被正确识别（`opencode debug agents`）
- [ ] Agent 描述清晰准确
- [ ] 可以正常切换到该 Agent
- [ ] System Prompt 正确加载

### 工具权限
- [ ] 允许的工具可以正常使用
- [ ] 禁用的工具无法使用
- [ ] 标记为 `ask` 的工具会触发确认

### 行为验证
- [ ] Agent 遵循指令中的 Workflow
- [ ] Agent 使用指定的工具组合
- [ ] 输出符合预期格式
- [ ] 能正确处理错误情况

### 边界情况
- [ ] 空输入处理
- [ ] 超长输入处理
- [ ] 特殊字符处理
- [ ] 多轮对话一致性
```

### 3.2 自动化测试框架

虽然 OpenCode 没有内置的 Agent 测试框架，但可以构建自己的测试：

```typescript
// tests/agent-test.ts
import { Agent } from "@opencode-ai/core"
import { Session } from "@opencode-ai/session"

describe("Test Runner Agent", () => {
  let agent: Agent.Info
  let session: Session.Info

  beforeAll(async () => {
    agent = await Agent.get("test-runner")
  })

  beforeEach(async () => {
    session = await Session.create({
      agent: agent.name,
    })
  })

  test("should have correct tools", async () => {
    const tools = await agent.tools()
    expect(tools).toContain("read")
    expect(tools).toContain("bash")
    expect(tools).not.toContain("write") // 假设没有 write 权限
  })

  test("should run tests on command", async () => {
    const result = await session.prompt({
      text: "Run tests for src/utils/math.ts",
    })

    // 验证调用了 bash 工具
    expect(result.parts).toContainEqual(
      expect.objectContaining({
        type: "tool",
        tool: "bash",
      })
    )
  })

  test("should not edit files without permission", async () => {
    const result = await session.prompt({
      text: "Fix the failing test by editing it",
    })

    // 验证没有调用 edit 工具（或被拒绝）
    const edits = result.parts.filter(
      (p) => p.type === "tool" && p.tool === "edit"
    )
    expect(edits.length).toBe(0)
  })
})
```

### 3.3 LLM-as-Judge 评估

使用另一个 LLM 来评估 Agent 的表现：

```typescript
// tests/agent-evaluator.ts
import { LLM } from "@opencode-ai/llm"

async function evaluateAgentResponse(
  agentResponse: string,
  criteria: string[]
): Promise<EvaluationResult> {
  const evaluationPrompt = `
You are an expert evaluator. Rate the following agent response on these criteria:
${criteria.map((c) => `- ${c}`).join("\n")}

Agent Response:
${agentResponse}

Provide scores (1-5) and brief justification for each criterion.
Format: JSON
`

  const result = await LLM.stream({
    model: "anthropic/claude-3-5-sonnet",
    messages: [{ role: "user", content: evaluationPrompt }],
  })

  return JSON.parse(result.text)
}

// 使用示例
const result = await evaluateAgentResponse(agentOutput, [
  "Follows the specified workflow",
  "Uses appropriate tools",
  "Output is clear and actionable",
  "Handles errors gracefully",
])
```

---

## 4. Agent 调试技巧

### 4.1 查看 System Prompt

```bash
# 查看最终发送给 LLM 的 System Prompt
opencode debug prompt --agent test-runner

# 查看完整消息（包括历史）
opencode debug messages --session sess_xxx
```

### 4.2 追踪工具调用

```bash
# 实时监控工具调用
opencode --print-logs 2>&1 | grep -E "(tool-call|tool-result)"

# 输出示例：
# [session.processor] tool-call: bash
# [tool.bash] execute: bun test
# [tool.bash] result: { exitCode: 0, output: "..." }
# [session.processor] tool-result: bash
```

### 4.3 模拟场景测试

创建测试场景来验证 Agent 行为：

```bash
# 创建测试项目
mkdir -p /tmp/test-project
cd /tmp/test-project
git init

# 创建一个有问题的测试文件
cat > math.test.ts << 'EOF'
import { test, expect } from "bun:test"
import { sum } from "./math"

test("sum should add numbers", () => {
  expect(sum(1, 2)).toBe(3)  // 这会失败，如果 sum 实现有问题
})

test("sum should handle negatives", () => {
  expect(sum(-1, 1)).toBe(0)
})
EOF

# 创建有 bug 的实现
cat > math.ts << 'EOF'
export function sum(a: number, b: number): number {
  // Bug: 忘记返回结果
  const result = a + b
}
EOF

# 启动 OpenCode 测试 Agent
opencode test-runner
# 然后输入: "Run tests and fix the failing ones"
```

### 4.4 对比测试

同时测试多个 Agent，对比表现：

```bash
# 创建测试脚本
#!/bin/bash

TEST_PROMPT="Find and fix the bug in src/utils/data.ts"

# 测试不同 Agent
echo "=== Testing with build agent ==="
opencode build --prompt "$TEST_PROMPT" --output build-result.md

echo "=== Testing with test-runner agent ==="
opencode test-runner --prompt "$TEST_PROMPT" --output test-runner-result.md

echo "=== Testing with explore agent ==="
opencode explore --prompt "$TEST_PROMPT" --output explore-result.md

# 对比结果
diff build-result.md test-runner-result.md
```

---

## 5. 最佳实践

### 5.1 Prompt 工程原则

```markdown
## Do's ✅

- 使用清晰的指令结构（编号列表）
- 提供具体示例
- 定义明确的输入/输出格式
- 指定错误处理方式
- 使用第三人称（"You are..."）

## Don'ts ❌

- 避免模糊指令（"do the right thing"）
- 不要过度限制（让 LLM 有一定灵活性）
- 避免过长的 Prompt（保持简洁）
- 不要包含实现细节（描述目标，不是方法）
```

### 5.2 工具权限设计

```yaml
# 最小权限原则
tools:
  # 只给必要的工具
  read: true
  glob: true
  
  # 敏感操作需要确认
  write: ask
  bash: ask
  
  # 禁止不必要的工具
  websearch: false
  webfetch: false
```

### 5.3 渐进式开发

```
Phase 1: 基础功能
├── 定义 Agent 角色
├── 配置基本工具
└── 编写核心指令

Phase 2: 边界处理
├── 添加错误处理指南
├── 定义边界情况响应
└── 测试异常情况

Phase 3: 优化迭代
├── 收集使用反馈
├── 调整 Prompt
└── 优化工具组合

Phase 4: 生产就绪
├── 完善文档
├── 添加示例
└── 性能优化
```

### 5.4 版本控制

```bash
# 将 Agent 配置纳入版本控制
git add .opencode/agents/
git commit -m "Add test-runner agent for automated testing"

# 使用语义化版本
# v1.0.0 - 初始版本
# v1.1.0 - 新增功能
# v1.1.1 - Bug 修复
```

---

## 6. 高级技巧

### 6.1 组合多个 Agent

```typescript
// 使用 Task 工具组合 Agent
async function multiAgentWorkflow(task: string) {
  // Step 1: Explore Agent 分析
  const analysis = await TaskTool.execute({
    subagent_type: "explore",
    prompt: `Analyze the codebase for: ${task}`,
  })

  // Step 2: Build Agent 实现
  const implementation = await TaskTool.execute({
    subagent_type: "build",
    prompt: `Implement based on analysis: ${analysis}`,
  })

  // Step 3: Test Runner Agent 验证
  const testResults = await TaskTool.execute({
    subagent_type: "test-runner",
    prompt: `Test the implementation: ${implementation}`,
  })

  return testResults
}
```

### 6.2 动态 Agent 选择

```typescript
// 根据任务特征自动选择 Agent
function selectAgent(task: string): string {
  if (task.includes("test") || task.includes("bug")) {
    return "test-runner"
  }
  if (task.includes("search") || task.includes("find")) {
    return "explore"
  }
  if (task.includes("plan") || task.includes("design")) {
    return "architect"
  }
  return "build"
}
```

### 6.3 Agent 性能监控

```typescript
// 追踪 Agent 性能指标
interface AgentMetrics {
  agentName: string
  totalCalls: number
  avgResponseTime: number
  successRate: number
  toolUsage: Record<string, number>
  tokenUsage: {
    input: number
    output: number
  }
}

async function collectMetrics(sessionId: string): Promise<AgentMetrics> {
  const session = await Session.get(sessionId)
  const messages = await MessageV2.list(sessionId)

  return {
    agentName: session.agent,
    totalCalls: messages.length,
    avgResponseTime: calculateAvgTime(messages),
    successRate: calculateSuccessRate(messages),
    toolUsage: countToolUsage(messages),
    tokenUsage: sumTokenUsage(messages),
  }
}
```

---

## 7. 常见陷阱与解决方案

### 7.1 Agent 不遵循指令

**症状**: Agent 无视 Prompt 中的指南

**解决方案**:
```markdown
# ❌ 差
Be careful when editing files.

# ✅ 好
## File Editing Policy

BEFORE editing any file:
1. Read the file first
2. Understand the context
3. Check for dependencies
4. Only then make minimal changes

AFTER editing:
1. Run tests to verify
2. Check for syntax errors
```

### 7.2 工具选择不当

**症状**: Agent 使用 bash 而不是专用工具

**解决方案**:
```markdown
## Tool Selection Guide

- For reading files: ALWAYS use `read` tool, NOT cat/head/tail
- For editing files: ALWAYS use `edit` tool, NOT sed/awk
- For searching: ALWAYS use `grep` or `glob`, NOT find
- For file operations: ALWAYS use dedicated tools, NOT bash
```

### 7.3 响应过长

**症状**: Agent 输出太多无关内容

**解决方案**:
```markdown
## Output Guidelines

- Be concise and direct
- Use bullet points for lists
- Show only relevant code snippets
- Focus on actionable information
- Avoid verbose explanations
```

---

## 8. 参考资源

### 8.1 内置 Agent 示例

```
packages/opencode/src/agent/prompt/
├── explore.txt      # 文件搜索专家
├── compaction.txt   # 摘要生成
├── summary.txt      # 会话总结
└── title.txt        # 标题生成
```

### 8.2 社区资源

- [OpenCode Agent Factory](https://lobehub.com/bg/skills/onichandame-skills-opencode-agent-factory) - Agent 开发 Skill
- [Plugin Development Guide](https://agent-skills.md/skills/v1truv1us/ai-eng-system/plugin-dev) - 插件开发指南
- [Creating Custom Agents](https://sergiocarracedo.es/creating-a-gym-ai-trainer-agent-with-opencode/) - 实战教程

### 8.3 测试框架参考

- [AI Agent Testing Best Practices](https://fail-kit.dev/blog/ai-agent-testing-best-practices)
- [Evaluating AI Agents](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)
- [Testing Frameworks for AI Agents](https://www.getmaxim.ai/articles/exploring-effective-testing-frameworks-for-ai-agents-in-real-world-scenarios/)

---

## 9. 总结

Agent 开发与测试的关键要点：

1. **清晰的定义** - 使用 Markdown + YAML 格式，明确定义 Agent 的角色和能力
2. **最小权限** - 只给必要的工具权限，敏感操作需要确认
3. **迭代测试** - 手动测试 + 自动化测试 + LLM-as-Judge 评估
4. **持续优化** - 收集反馈，调整 Prompt，优化性能
5. **版本控制** - 将 Agent 配置纳入版本控制，便于团队协作

---

**Happy Agent Building! 🤖**
