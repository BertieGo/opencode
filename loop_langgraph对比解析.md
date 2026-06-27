# Agentic Loop 对比解析：opencode_demo vs LangGraph/deerflow

## 核心问题：Agent 如何知道任务没完成、要继续？

### 停止信号的本质

LLM 通过**有没有输出 `tool_calls`** 来表达意图：

```
有 tool_calls  → "我还没完，需要执行工具"
无 tool_calls  → "我完了，这是最终答案"
```

框架（LangGraph 或自己写的 while）只负责读这个信号，不理解任务语义。

---

## 消息累积的完整过程

每一轮 LLM 拿到的都是完整历史，靠上下文感知"已做了什么、还差什么"：

```
messages = [
  {role: user,      content: "帮我做1、2、3"},
  {role: assistant, tool_calls: [{name: "write_todos", ...}]},   # 轮1：规划
  {role: tool,      content: "todo updated"},
  {role: assistant, tool_calls: [{name: "read", args: {...}}]},  # 轮2：执行1
  {role: tool,      content: "文件内容..."},
  {role: assistant, tool_calls: [{name: "write", ...}]},         # 轮3：执行2
  {role: tool,      content: "file written"},
  {role: assistant, content: "全部完成了"},  # ← 无 tool_calls → END
]
```

停止的判断看的是**最后一条 AI 消息有没有 `tool_calls`**，跟 tool result 本身无关。

---

## opencode_demo.py（改造前）

```python
# 最多只有两次 LLM 调用，无法支持真正的多步任务
llm_response = self.llm.chat(...)
tool_calls = self._parse_tool_calls(ai_content)

if tool_calls:
    执行工具
    final_response = self.llm.chat(...)  # 第二次，直接返回
    return final_response
else:
    return ai_content
```

**问题**：做完步骤1之后就返回了，无法自动继续做2、3。

---

## opencode_demo.py（改造后）

```python
for iteration in range(max_iterations):
    llm_response = self.llm.chat(system, messages)
    tool_calls = self._parse_tool_calls(ai_content)

    if not tool_calls:
        return ai_content          # ← 无 tool_calls，任务完成

    # 执行工具，把结果追加到 messages，进入下一轮
    messages.append({role: assistant, content: ai_content})
    messages.append({role: user, content: tool_results})
```

---

## LangGraph/deerflow 的实现

关键代码在 `langgraph/prebuilt/chat_agent_executor.py`：

```python
def should_continue(state) -> str:
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return END      # ← 无 tool_calls，结束

    return "tools"      # ← 有 tool_calls，去执行工具，然后再回来
```

这是图的**条件边**：`agent 节点 → should_continue() → tools 节点 或 END`

---

## deerflow 相比 opencode_demo 多了什么

**只多了 `write_todos` 这一个工具**，用来显式规划任务列表：

```
用户："帮我做1、2、3"
  ↓
LLM 调用 write_todos([
  {content: "做1", status: "in_progress"},
  {content: "做2", status: "pending"},
  {content: "做3", status: "pending"},
])
  ↓
做完1 → write_todos 更新：1=completed, 2=in_progress
做完2 → write_todos 更新：2=completed, 3=in_progress
做完3 → write_todos 更新：3=completed → 不再调工具 → END
```

停止机制完全一样，`write_todos` 只是让 LLM 的任务感知更可靠，不是新的停止机制。

---

## 中间件的作用（安全网，非主路径）

| 中间件 | 作用 |
|--|--|
| `TodoMiddleware.before_model` | 对话太长被截断时，补注 todo 列表提醒，让 LLM 不忘记未完成的任务 |
| `LoopDetectionMiddleware.after_model` | 同一组 tool_calls 重复 ≥3 次注入警告，≥5 次直接剥掉 `tool_calls` 强制结束 |

---

## "LLM 自己判断"的真相

LLM 并没有逻辑代码判断"任务完没完"，这个能力来自**训练**（RLHF + instruction tuning）：

- 模型被喂了大量示例：任务未完 → 输出 tool_calls，任务完成 → 输出纯文本
- 推理时模型生成 token，自然产生两种形态之一
- 框架代码只是读这个结果做路由，不参与判断

---

## 一句话总结

> `tool_calls` 有没有，是 LLM 和框架之间唯一的"完成信号"。todo 列表是帮 LLM 记清楚自己要做什么，loop detection 是防止 LLM 卡死，但最终的停止判断永远只有这一条：**无 tool_calls → END**。
