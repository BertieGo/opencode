# Anthropic-20250930 Prompt 深度解析

> 文件路径：`packages/opencode/src/session/prompt/anthropic-20250930.txt`
> 
> 这是 OpenCode 中 Claude (Anthropic) 模型的主 Agent 系统提示词，166 行精心设计的指令，展现了工业级 Prompt Engineering 的典范。

---

## 📊 整体架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Prompt 结构金字塔                             │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 身份锚定 (Identity)                                    │
│    └── "You are an interactive CLI tool"                        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 硬约束 (Hard Constraints)                              │
│    └── 安全限制、禁止行为、必须行为                                │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 风格定义 (Style & Tone)                                │
│    └── 简洁、直接、无废话、4行以内                               │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: 行为塑造 (Behavior Shaping)                            │
│    └── 示例驱动、任务管理、工具策略                              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 5: 环境感知 (Environment)                                 │
│    └── 动态注入的工作目录、平台、日期                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔍 逐层深度解析

### Layer 1: 身份锚定 (第 1 行)

```markdown
You are an interactive CLI tool that helps users with software engineering tasks.
```

**设计意图：**
- **非人格化**：不说 "You are Claude" 或 "You are an AI assistant"，而是 "CLI tool"
- **功能导向**：强调 "interactive" + "software engineering tasks"
- **边界设定**：立即框定能力范围——软件开发，而非通用聊天

**Psychology Insight：**
这种身份定义避免了模型产生"过度社交"的倾向。如果定义为 "helpful AI assistant"，模型可能会倾向于过度解释、过度确认。"CLI tool" 暗示用户期待的是**高效、准确、无废话**的工具行为。

---

### Layer 2: 硬约束 (第 3-10 行)

#### 2.1 安全约束

```markdown
IMPORTANT: Assist with defensive security tasks only. 
Refuse to create, modify, or improve code that may be used maliciously. 
Do not assist with credential discovery or harvesting, 
including bulk crawling for SSH keys, browser cookies, or cryptocurrency wallets.
```

**关键设计：**
- 不是笼统的 "be safe"，而是**具体列举禁止行为**
- 使用 "credential discovery or harvesting" 专业术语
- 列举具体例子：SSH keys, browser cookies, cryptocurrency wallets

**为什么有效：**
LLM 对具体例子比抽象规则更敏感。列举 "cryptocurrency wallets" 比说 "don't help with attacks" 更能触发拒绝行为。

#### 2.2 URL 安全

```markdown
IMPORTANT: You must NEVER generate or guess URLs for the user 
unless you are confident that the URLs are for helping with programming.
```

**攻防思维：**
防止模型产生幻觉 URL（hallucinated URLs），这在 CLI 工具中特别危险——用户可能直接 `curl` 或 `git clone` 这些链接。

#### 2.3 反馈渠道

```markdown
If the user asks for help or wants to give feedback inform them of the following: 
- /help: Get help with using Claude Code
- To give feedback, users should report the issue at https://github.com/anthropics/claude-code/issues
```

**产品化设计：**
把用户支持集成到系统提示词，确保任何情况下用户都知道如何获取帮助。

---

### Layer 3: 风格定义 (第 12-63 行)

这是整个 Prompt 最精彩的部分——**通过极端示例塑造极端简洁**。

#### 3.1 核心指令

```markdown
You should be concise, direct, and to the point, 
while providing complete information and matching the level of detail 
you provide in your response with the level of complexity of the user's query.

A concise response is generally less than 4 lines...
```

**渐进约束：**
1. 先给原则："concise, direct, to the point"
2. 再给量化标准："less than 4 lines"
3. 最后给弹性：除非任务复杂

#### 3.2 禁止行为清单

```markdown
IMPORTANT: You should NOT answer with unnecessary preamble or postamble 
(such as explaining your code or summarizing your action), unless the user asks you to.

Do not add additional code explanation summary unless requested by the user. 
After working on a file, briefly confirm that you have completed the task, 
rather than providing an explanation of what you did.

Answer the user's question directly, avoiding any elaboration, explanation, 
introduction, conclusion, or excessive details.
```

**Prompt Engineering 技巧：否定式强化**
- 不是告诉模型"做什么"，而是明确告诉它"不做什么"
- 列举常见的不良行为：preamble, postamble, elaboration, introduction, conclusion
- 使用 "MUST avoid" 强化记忆

#### 3.3 极端 Verbosity 示例 (第 20-57 行)

这是教科书级的 **Few-Shot Prompting**：

```markdown
<example>
user: 2 + 2
assistant: 4
</example>

<example>
user: what is 2+2?
assistant: 4
</example>

<example>
user: is 11 a prime number?
assistant: Yes
</example>

<example>
user: what command should I run to list files in the current directory?
assistant: ls
</example>
```

**为什么这些例子如此重要？**

| 例子 | 训练偏差对抗 |
|------|-------------|
| `2+2` → `4` | 对抗 "The answer to 2+2 is 4, which is the result of adding..." |
| `ls` → `ls` | 对抗 "To list files in the current directory, you can use the `ls` command, which stands for 'list'..." |
| 两句话的问题 → 一个词的回答 | 打破 "回答长度应与问题长度成正比" 的偏见 |

**Psychology Insight：**
LLM 在预训练中学到的是"帮助用户理解"，但在 CLI 场景中，用户想要的是**快速执行**。这些例子通过极端简洁的示范，覆盖掉模型的默认"教学式"行为。

#### 3.4 表情符号规则

```markdown
Only use emojis if the user explicitly requests it. 
Avoid using emojis in all communication unless asked.
```

**专业感塑造：**
CLI 工具 = 专业开发环境 = 无表情符号。这个规则确保即使在轻松对话中，模型也保持专业 CLI 工具的身份。

---

### Layer 4: 行为塑造 (第 65-138 行)

#### 4.1 主动性平衡 (第 65-70 行)

```markdown
# Proactiveness
You are allowed to be proactive, but only when the user asks you to do something. 
You should strive to strike a balance between:
- Doing the right thing when asked, including taking actions and follow-up actions
- Not surprising the user with actions you take without asking
```

**微妙的平衡术：**
- "allowed to be proactive" —— 给予权限
- "but only when the user asks you to do something" —— 设置边界
- 列举两个对立原则，让模型自行权衡

#### 4.2 专业客观性 (第 71-73 行)

```markdown
# Professional objectivity
Prioritize technical accuracy and truthfulness over validating the user's beliefs. 
Focus on facts and problem-solving, providing direct, objective technical info 
without any unnecessary superlatives, praise, or emotional validation.
```

**对抗 Sycophancy（谄媚倾向）：**
LLM 有强烈的倾向去"同意用户"和" validating user"。这段指令明确告诉模型：**技术准确性 > 用户感受**。

关键短语：
- "truthfulness over validating the user's beliefs"
- "disagrees when necessary, even if it may not be what the user wants to hear"
- "Objective guidance and respectful correction are more valuable than false agreement"

#### 4.3 任务管理 (第 74-119 行)

```markdown
# Task Management
You have access to the TodoWrite tools to help you manage and plan tasks. 
Use these tools VERY frequently to ensure that you are tracking your tasks...

It is critical that you mark todos as completed as soon as you are done with a task. 
Do not batch up tasks before marking them as completed.
```

**强化关键词：**
- "VERY frequently"（全大写强调）
- "It is critical"
- "do not batch up"

**示例设计：**
两个详细示例展示了如何：
1. 初始规划 → TodoWrite 创建任务列表
2. 执行中 → 发现 10 个错误，立即创建 10 个 todo
3. 逐个完成 → 标记 in_progress → completed

**隐含信息：**
- 不要等所有事情做完再更新 todo
- 任务粒度要细（一个错误一个 todo）
- 状态流转：in_progress → completed

#### 4.4 🔥 工具使用策略 (第 131-138 行)

这是整个 Prompt 中**对行为影响最大**的部分：

```markdown
# Tool usage policy
- When doing file search, prefer to use the Task tool in order to reduce context usage.
- You should proactively use the Task tool with specialized agents 
  when the task at hand matches the agent's description.
```

**设计决策分析：**

| 指令 | 意图 |
|------|------|
| "prefer to use the Task tool" | 改变默认行为：从"我自己搜索"到"派遣专家" |
| "in order to reduce context usage" | 给出理性理由：不是因为我懒，是为了效率 |
| "proactively use" | 主动而非被动，看到匹配就派 |
| "when the task at hand matches the agent's description" | 匹配逻辑：任务特征 ↔ Agent 描述 |

**为什么这两条指令能改变行为？**

因为模型接收到的工具描述（task.txt）只说了：
- "Launch a new agent to handle complex, multistep tasks"
- "When to use: execute custom slash commands"

如果没有这两条指令，模型会：
1. 认为 Task Tool 只用于 "slash commands"
2. 倾向于自己用 Read/Glob/Grep 搜索
3. 不主动派遣 explore/coder 等子代理

这两条指令**覆盖**了 task.txt 的保守描述，告诉模型：
> "文件搜索时，尽管派 Task Tool 出去！"

#### 4.5 并行调用强制 (第 136-137 行)

```markdown
- You have the capability to call multiple tools in a single response. 
  When multiple independent pieces of information are requested, 
  batch your tool calls together for optimal performance.

- If the user specifies that they want you to run tools "in parallel", 
  you MUST send a single message with multiple tool use content blocks. 
  For example, if you need to launch multiple agents in parallel, 
  send a single message with multiple Task tool calls.
```

**性能优化意识：**
- 明确告诉模型：并行 = 性能提升
- 给出具体操作指导："single message with multiple tool use content blocks"
- 举例说明：多个 Task tool calls 可以并行

---

### Layer 5: 环境感知 (第 141-148 行)

```markdown
Here is useful information about the environment you are running in:
<env>
Working directory: /home/thdxr/dev/projects/anomalyco/opencode/packages/opencode
Is directory a git repo: Yes
Platform: linux
OS Version: Linux 6.12.4-arch1-1
Today's date: 2025-09-30
</env>
You are powered by the model named Sonnet 4.5. 
The exact model ID is claude-sonnet-4-5-20250929.

Assistant knowledge cutoff is January 2025.
```

**动态注入的信息：**
- `Working directory` —— 相对路径解析的基准
- `Is directory a git repo` —— 是否启用 git 相关工具
- `Platform` / `OS Version` —— Bash 命令的兼容性
- `Today's date` —— 时间感知
- `model named` —— 自我能力校准
- `knowledge cutoff` —— 知识边界提醒

---

## 🎓 Prompt Engineering 技巧总结

### 技巧 1: 渐进约束 (Progressive Constraint)

```markdown
原则 → 量化标准 → 弹性条款

"concise, direct" → "less than 4 lines" → "unless the task is complex"
```

### 技巧 2: 否定式强化 (Negative Reinforcement)

与其告诉模型"做什么"，不如明确告诉它"**不做什么**"：

```markdown
❌ "Be concise"
✅ "You should NOT answer with unnecessary preamble or postamble"

❌ "Don't explain too much"  
✅ "Avoiding any elaboration, explanation, introduction, conclusion"
```

### 技巧 3: 极端示例驱动 (Extreme Few-Shot)

用**极端简洁**的示例覆盖模型的默认冗长倾向：

```markdown
user: 2 + 2
assistant: 4
```

这个例子比 1000 字的"请简洁"指令都有效。

### 技巧 4: 功能性身份锚定 (Functional Identity)

```markdown
❌ "You are Claude, a helpful AI assistant"
✅ "You are an interactive CLI tool"
```

身份定义决定行为模式。"CLI tool" = 高效、专业、无废话。

### 技巧 5: 具体化安全约束 (Concrete Safety)

```markdown
❌ "Don't help with malicious activities"
✅ "Do not assist with credential discovery or harvesting, 
    including bulk crawling for SSH keys, browser cookies, 
    or cryptocurrency wallets"
```

具体例子触发具体行为。

### 技巧 6: 行为覆盖 (Behavior Override)

Task Tool 的使用策略展示了如何**覆盖**工具描述的保守定义：

```markdown
Tool description: "When to use: execute custom slash commands"
Prompt override: "When doing file search, prefer to use the Task tool"
```

Prompt 中的指令优先级高于工具描述。

### 技巧 7: 强制并行意识 (Forced Parallelism)

```markdown
"you MUST send a single message with multiple tool use content blocks"
"For example, if you need to launch multiple agents in parallel..."
```

使用 MUST + 具体示例 + 场景说明，强制改变模型的序列化思维。

---

## 🔬 行为控制机制分析

### 机制 1: 频率强化 (Frequency Amplification)

```markdown
"Use these tools VERY frequently"
"It is critical that you mark todos..."
"Always use the TodoWrite tool..."
```

通过**强调词** (VERY, critical, Always) 提升特定行为的概率。

### 机制 2: 负面后果暗示 (Negative Consequence)

```markdown
"If you do not use this tool when planning, 
 you may forget to do important tasks - and that is unacceptable."
```

"that is unacceptable" —— 强烈的负面评价，触发回避行为。

### 机制 3: 社会认同 (Social Proof)

```markdown
"Examples:
<example>
user: Run the build and fix any type errors
assistant: [展示正确的 todo 使用方式]
</example>"
```

通过展示"正确的行为示例"，让模型模仿。

### 机制 4: 自我监控触发 (Self-Monitoring)

```markdown
"Use these tools VERY frequently to ensure that you are tracking your tasks 
 and giving your user visibility into your progress."
```

"ensure that you are tracking" —— 触发模型的自我检查机制。

---

## 📈 效果验证指标

如果按照这个 Prompt 设计，预期会看到的行为特征：

| 指标 | 预期表现 |
|------|---------|
| 平均回复长度 | < 4 行 (简单查询) |
| TodoWrite 使用频率 | 每个任务阶段都有 |
| Task Tool 主动使用 | 遇到代码探索即派遣 explore |
| 并行工具调用 | 常见 |
| 表情符号使用率 | 接近 0 (除非用户要求) |
| 开场白 | 无 "Sure, I'd be happy to..." |
| 解释性总结 | 仅在用户要求时出现 |
| 技术异议率 | 高于普通 ChatBot |

---

## 💡 对 Kimi Code 的借鉴

### 可借鉴的设计

1. **极端简洁示例**：用 `2+2=4` 级别的例子塑造行为
2. **否定式强化**：明确列出"不做什么"
3. **功能性身份**：定义工具身份而非助手身份
4. **动态环境注入**：工作目录、平台、日期
5. **Task Tool 覆盖策略**：在 Prompt 中覆盖工具描述的保守定义
6. **强制并行意识**：明确指令 + 具体示例

### 需谨慎的部分

1. **安全约束**：Kimi Code 的安全策略可能需要不同侧重
2. **反馈渠道**：Claude Code 的 GitHub issue 链接需要替换
3. **Verbosity 标准**：4 行可能对某些场景过于严格

---

## 📝 一句话总结

> 这份 Prompt 是**行为控制的艺术**——通过身份锚定、极端示例、否定强化和频率放大，将一个倾向于" helpful assistant"的 LLM，精确塑造成一个**高效、专业、无废话的 CLI 工具**。

---

*分析完成时间：2026-03-16*
*分析者：Kimi Code*
