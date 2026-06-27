# 待思考项记录

> 记录 OpenCode 技术文档撰写过程中的待深入研究项

---

## 1. BatchTool 的实现

### 背景
BatchTool 是一个实验性工具，允许 AI 在一个请求中并行执行多个工具调用（最多 25 个）。

### 待思考的问题

- [ ] **执行模型**：是真正的并行执行（Promise.all）还是伪并行？
- [ ] **错误处理**：如果其中一个工具失败，其他工具的结果如何处理？
- [ ] **超时机制**：整体有超时还是每个子调用有独立超时？
- [ ] **结果合并**：多个工具的结果如何格式化返回给 AI？
- [ ] **权限检查**：是每个子调用单独检查权限，还是批量检查？
- [ ] **上下文隔离**：子调用之间是否共享上下文？
- [ ] **嵌套限制**：为什么不能嵌套 batch（BatchTool 本身不能在 batch 中）？

### 相关代码位置
```
packages/opencode/src/tool/batch.ts
```

### 优先级
🔶 中 - 有助于理解工具系统的并发设计

---

## 2. 大量 Tools、Skills、MCPs 的提示词规划策略

### 背景
OpenCode 支持：
- 10+ 内置工具
- 自定义工具（来自文件/插件）
- MCP 工具（数量不定）
- Skills（数量不定）

这些都会转换为 prompt 的一部分发送给 LLM。

### 待思考的问题

- [ ] **分层策略**：工具描述是否应该分层加载（基础工具 vs 扩展工具）？
- [ ] **动态选择**：AI 是否可以在对话过程中动态请求加载更多工具？
- [ ] **摘要机制**：当工具太多时，是否可以对工具描述进行 AI 摘要？
- [ ] **使用统计**：是否应该根据历史使用频率排序工具描述？
- [ ] **领域分组**：是否按功能领域（文件操作、代码编辑、搜索等）分组工具？
- [ ] **模型适配**：不同模型（Claude、GPT）对工具描述的偏好是否不同？
- [ ] **MCP 发现**：MCP 工具是否应该在第一次对话时只提供概览，需要时再详细加载？
- [ ] **Skill 缓存**：加载过的 Skill 是否可以缓存，避免重复加载？
- [ ] **Token 预算**：是否应该给 tools/skills 设置一个 token 预算上限？

### 当前机制回顾

| 机制 | 说明 |
|------|------|
| 权限过滤 | Agent 配置中禁用不需要的工具 |
| 模型过滤 | 根据模型类型选择工具（如 GPT 用 apply_patch） |
| Skill 延迟加载 | 只加载列表，需要时通过 skill 工具加载详情 |
| MCP 选择性启用 | 只有配置的服务器才会加载 |

### 优先级
🔴 高 - 涉及系统核心性能和大规模扩展性

---

## 3. 主循环（Main Loop）机制与设计目的

### 背景
主循环是 OpenCode 对话流程的核心控制结构，位于 `packages/opencode/src/session/prompt.ts` 的 `loop()` 函数（第 276 行开始）。

### 当前机制

```
while (true) {                          // 无限循环
    step++                              // 每轮迭代递增
    
    // 1. 上下文溢出检查
    if (isOverflow()) {
        triggerCompaction()             // 触发 AI 摘要
        continue                        // 重新开始循环
    }
    
    // 2. 检查待处理的子任务
    if (hasPendingSubtask()) {
        executeSubtask()                // 执行子 Agent
        continue                        // 子任务完成后再继续
    }
    
    // 3. 检查待处理的 compaction
    if (hasPendingCompaction()) {
        processCompaction()             // 执行上下文压缩
        continue
    }
    
    // 4. 正常对话流程
    assembleSystemPrompt()              // 组装 System Prompt
    resolveTools()                      // 获取可用工具
    
    result = await callLLM()            // 调用 LLM
    
    if (result === "stop") break        // 对话结束
    if (result === "compact") {         // 需要压缩
        createCompactionTask()
        continue
    }
    // 否则继续下一轮（AI 调用了工具）
}
```

### 设计目的分析

| 设计决策 | 目的 |
|---------|------|
| **while(true) 无限循环** | 支持多轮工具调用直到任务完成 |
| **step 计数器** | 限制最大迭代次数（防止无限循环） |
| **前置条件检查** | 在进入 LLM 调用前处理所有特殊情况 |
| **continue 模式** | 处理完异常情况后重新开始，确保状态一致 |
| **分离 subtask/compaction 处理** | 避免与正常对话流程耦合 |

### 待思考的问题

- [ ] **状态机 vs 循环**：当前是命令式循环，是否可以改为状态机模式？
- [ ] **错误恢复**：如果某一步骤失败，如何从错误状态恢复？
- [ ] **可观测性**：循环执行过程如何更好地追踪和调试？
- [ ] **并行化**：是否可以并行执行某些检查（如工具解析和 prompt 组装）？
- [ ] **中断处理**：用户取消时如何优雅地退出循环？
- [ ] **重试策略**：LLM 调用失败时的重试逻辑应该放在循环内还是循环外？

### 相关代码
- `packages/opencode/src/session/prompt.ts` 第 276-734 行

### 优先级
🟡 中 - 有助于理解系统架构和可能的优化方向

---

## 4. Subagent（子 Agent）机制详解

### 背景
Subagent 是 OpenCode 实现任务分解和并行处理的核心机制。通过 Task 工具，主 Agent 可以创建子会话来执行特定任务。

### 已了解的内容

| 方面 | 说明 |
|------|------|
| **创建方式** | 用户通过 `@agent_name` 提及 或 AI 调用 `task` 工具 |
| **子会话** | 通过 `Session.create({ parentID: ... })` 创建，与父会话隔离 |
| **权限限制** | 子 Agent 默认不能操作 todo 列表，不能创建嵌套子 Agent |
| **执行流程** | 主循环检测到 subtask part → 创建子会话 → 执行 → 返回结果 |

### 待深入思考的问题

- [ ] **生命周期管理**：子会话何时创建、何时销毁？未完成的子会话如何处理？
- [ ] **结果合并**：子 Agent 的结果如何格式化并合并回父会话？
- [ ] **错误传播**：子 Agent 执行失败时，错误如何传播给父 Agent？
- [ ] **上下文共享**：父子会话之间可以共享哪些上下文？如何传递？
- [ ] **并发控制**：多个 subagent 同时执行时的并发限制？
- [ ] **调试体验**：用户如何在 UI 中查看子 Agent 的执行状态？
- [ ] **explore vs general**：两种子 Agent 的具体区别和使用场景？
- [ ] **hidden agent**：compaction、title、summary 三个 hidden agent 的工作流程？

### 相关代码位置
```
packages/opencode/src/tool/task.ts          # Task 工具实现
packages/opencode/src/session/prompt.ts     # loop() 中 subtask 处理（第 306-430 行）
packages/opencode/src/agent/prompt/         # explore.txt, compaction.txt, summary.txt, title.txt
```

### 优先级
🟢 高 - 核心架构机制，影响任务分解能力

---

## 其他备忘

- 检查 `OPENCODE_EXPERIMENTAL_BATCH_TOOL` 环境变量的具体处理逻辑
- 了解 MCP 协议中的 tool list 更新机制
- 研究其他 AI 编码工具（如 Claude Code、Cline）的工具管理策略
