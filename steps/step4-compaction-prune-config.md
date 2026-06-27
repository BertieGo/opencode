# Compaction 与 Prune 配置机制详解

> 本文详细解释 OpenCode 中两种上下文优化机制的配置方式和相互关系。

---

## 📋 概述

OpenCode 提供了两种上下文优化机制：

| 机制 | 目的 | 触发时机 | 处理方式 |
|------|------|----------|----------|
| **Compaction（压缩）** | 防止上下文溢出 | Token 接近上限时 | AI 总结生成摘要 |
| **Prune（剪枝）** | 清理无用输出 | 每次 step 后自动 | 删除旧工具输出 |

**关键区别**：
- Compaction 是**救命机制**——防止崩溃
- Prune 是**优化机制**——日常清理

---

## ⚙️ 配置结构

在 `~/.opencode/opencode.yml` 中的配置：

```yaml
compaction:
  auto: true        # 是否启用自动压缩（默认: true）
  prune: true       # 是否启用剪枝（默认: true）
  reserved: 20000   # 预留缓冲 token 数（默认: 20000）
```

### Schema 定义

```typescript
// packages/opencode/src/config/config.ts 第 1169-1180 行

compaction: z
  .object({
    auto: z.boolean().optional()
      .describe("Enable automatic compaction when context is full (default: true)"),
    
    prune: z.boolean().optional()
      .describe("Enable pruning of old tool outputs (default: true)"),
    
    reserved: z.number().int().min(0).optional()
      .describe("Token buffer for compaction. Leaves enough window to avoid overflow during compaction."),
  })
  .optional()
```

---

## 🔧 环境变量覆盖

除了配置文件，还可以通过环境变量控制：

```typescript
// packages/opencode/src/config/config.ts 第 250-255 行

if (Flag.OPENCODE_DISABLE_AUTOCOMPACT) {
  result.compaction = { ...result.compaction, auto: false }
}
if (Flag.OPENCODE_DISABLE_PRUNE) {
  result.compaction = { ...result.compaction, prune: false }
}
```

| 环境变量 | 作用 | 等价配置 |
|----------|------|----------|
| `OPENCODE_DISABLE_AUTOCOMPACT=1` | 禁用自动压缩 | `compaction.auto: false` |
| `OPENCODE_DISABLE_PRUNE=1` | 禁用剪枝 | `compaction.prune: false` |

---

## 🎯 Compaction（压缩）机制

### 配置项

```yaml
compaction:
  auto: true        # 启用/禁用
  reserved: 20000   # 预留空间
```

### 工作原理

```typescript
// packages/opencode/src/session/compaction.ts 第 33-49 行

export async function isOverflow(input) {
  const config = await Config.get()
  
  // 1. 检查是否禁用
  if (config.compaction?.auto === false) return false
  
  // 2. 获取模型限制
  const context = input.model.limit.context
  
  // 3. 计算已用 token
  const count = input.tokens.input + 
                input.tokens.output + 
                input.tokens.cache.read + 
                input.tokens.cache.write
  
  // 4. 计算可用阈值
  const reserved = config.compaction?.reserved ?? 20000
  const usable = context - reserved
  
  // 5. 判断是否超限
  return count >= usable
}
```

### 触发流程

```
用户发送消息
    │
    ▼
已用 tokens: 185K
模型限制: 200K
预留: 20K
可用阈值: 180K (200K - 20K)
    │
    ▼
185K >= 180K? 
    │
    ├── 是 → 触发 Compaction
    │         ├── 召唤 compaction Agent
    │         ├── AI 总结历史对话
    │         ├── 生成摘要消息
    │         └── 原始历史被标记为 compacted
    │
    └── 否 → 继续正常处理
```

### 配置影响

| 配置 | 效果 |
|------|------|
| `auto: true`（默认） | Token 接近上限时自动压缩 |
| `auto: false` | 不自动压缩，可能导致 API 报错 |
| `reserved: 20000`（默认） | 预留 20K 给 AI 回复 |
| `reserved: 40000` | 预留更多空间，更早触发压缩 |

---

## ✂️ Prune（剪枝）机制

### 配置项

```yaml
compaction:
  prune: true       # 启用/禁用
```

### 工作原理

```typescript
// packages/opencode/src/session/compaction.ts 第 59-100 行

export async function prune(input: { sessionID: SessionID }) {
  const config = await Config.get()
  
  // 1. 检查是否禁用
  if (config.compaction?.prune === false) return
  
  const msgs = await Session.messages({ sessionID: input.sessionID })
  let total = 0
  let pruned = 0
  const toPrune = []
  
  // 2. 从后往前遍历（最新的消息）
  loop: for (let msgIndex = msgs.length - 1; msgIndex >= 0; msgIndex--) {
    const msg = msgs[msgIndex]
    
    // 3. 保护最近 2 轮对话
    if (msg.info.role === "user") turns++
    if (turns < 2) continue
    
    // 4. 如果已经压缩过了，停止
    if (msg.info.role === "assistant" && msg.info.summary) break loop
    
    // 5. 遍历消息的所有部分
    for (let partIndex = msg.parts.length - 1; partIndex >= 0; partIndex--) {
      const part = msg.parts[partIndex]
      
      // 6. 找到已完成的工具调用
      if (part.type === "tool" && part.state.status === "completed") {
        // 7. 保护特定工具（如 skill）
        if (PRUNE_PROTECTED_TOOLS.includes(part.tool)) continue
        
        // 8. 计算 token 数
        const estimate = Token.estimate(part.state.output)
        total += estimate
        
        // 9. 如果超过保护阈值 40K，标记为可剪枝
        if (total > PRUNE_PROTECT) {
          pruned += estimate
          toPrune.push(part)
        }
      }
    }
  }
  
  // 10. 如果能节省至少 20K，执行剪枝
  if (pruned > PRUNE_MINIMUM) {
    for (const part of toPrune) {
      part.state.time.compacted = Date.now()
      await Session.updatePart(part)
    }
  }
}
```

### 硬编码参数

```typescript
// packages/opencode/src/session/compaction.ts 第 51-54 行

const PRUNE_MINIMUM = 20_000      // 至少剪 20K 才值得执行
const PRUNE_PROTECT = 40_000      // 保护最近 40K 的上下文
const PRUNE_PROTECTED_TOOLS = ["skill"]  // 这些工具的输出不剪枝
```

### 触发时机

```typescript
// packages/opencode/src/session/prompt.ts 第 723 行

// 在主循环的每次迭代后调用
SessionCompaction.prune({ sessionID })
```

**触发流程**：

```
每次 step 结束后
    │
    ▼
检查是否启用 prune
    │
    ├── 禁用 → 跳过
    │
    └── 启用 → 从后往前扫描消息
              │
              ├── 跳过最近 2 轮对话（保护）
              ├── 跳过已压缩的消息
              ├── 跳过 skill 工具输出
              │
              └── 对于其他完成的工具调用：
                    ├── 计算输出 token 数
                    ├── 累计超过 40K 保护阈值？
                    │     ├── 是 → 标记为可剪枝
                    │     └── 否 → 继续扫描
                    │
                    └── 累计可剪枝 > 20K？
                          ├── 是 → 执行剪枝
                          └── 否 → 放弃（不值得）
```

---

## 🔗 两者的关系

### 1. 独立配置

```yaml
# 场景 1: 全部启用（默认）
compaction:
  auto: true   # ✓ 启用压缩
  prune: true  # ✓ 启用剪枝

# 场景 2: 只启用压缩
compaction:
  auto: true   # ✓ 启用压缩
  prune: false # ✗ 禁用剪枝

# 场景 3: 只启用剪枝
compaction:
  auto: false  # ✗ 禁用压缩
  prune: true  # ✓ 启用剪枝

# 场景 4: 全部禁用（不推荐）
compaction:
  auto: false  # ✗ 禁用压缩
  prune: false # ✗ 禁用剪枝
```

### 2. 协同工作流程

```
对话进行中
    │
    ├── 每次 step 后 ──────────────────► Prune（轻量清理）
    │                                    ├── 删除旧工具输出
    │                                    ├── 保留最近 2 轮
    │                                    └── 节省空间：中等
    │
    └── Token 接近上限时 ──────────────► Compaction（重度压缩）
                                         ├── AI 总结历史
                                         ├── 生成摘要
                                         └── 节省空间：90%+
```

### 3. 互相影响

| 情况 | 结果 |
|------|------|
| Prune 清理了大量空间 | 可能推迟 Compaction 的触发 |
| Compaction 已执行 | Prune 会跳过已压缩的消息 |
| 两者都禁用 | 长对话必然溢出报错 |
| 只启用 Prune | 日常清理有效，但极端情况仍会溢出 |
| 只启用 Compaction | 能有效防止溢出，但频繁压缩影响体验 |

---

## 📊 配置建议

### 默认配置（推荐大部分用户）

```yaml
# 不需要任何配置，使用默认值
# compaction.auto: true
# compaction.prune: true
# compaction.reserved: 20000
```

### 长对话场景（如代码审查）

```yaml
compaction:
  auto: true
  prune: true
  reserved: 30000    # 预留更多空间，更早压缩
```

### 短对话场景（如快速问答）

```yaml
compaction:
  auto: true
  prune: false       # 短对话不需要剪枝
```

### 调试模式（查看完整历史）

```yaml
compaction:
  auto: false        # 禁用压缩，可能溢出
  prune: false       # 禁用剪枝
```

**或使用环境变量**：
```bash
OPENCODE_DISABLE_AUTOCOMPACT=1 OPENCODE_DISABLE_PRUNE=1 opencode
```

---

## 🎭 形象比喻

### Compaction = 搬家时的大清理

> 你住在一个 200平米的房子里（上下文窗口），东西越来越多。
> 
> 当占用达到 180平米时，你决定**请专业整理师**（compaction Agent）来帮忙：
> - 把旧文件扫描成电子版（生成摘要）
> - 扔掉原始纸张（标记为 compacted）
> - 整理师给你一个目录清单（摘要消息）
> 
> 这样你腾出了 90% 的空间！

### Prune = 日常扔垃圾

> 每天你都会产生一些垃圾（工具输出）：
> - 快递包装（bash 输出）
> - 外卖盒（read 输出）
> 
> **每天自动清理**（每次 step 后）：
> - 扔掉超过 2 天的垃圾（保护最近 2 轮）
> - 但保留重要文件（skill 工具）
> - 如果垃圾不够多（< 20K），就不值得扔

### 两者的配合

> **日常**：自动扔垃圾（Prune），保持房间整洁
> 
> **紧急**：请整理师（Compaction），防止房间爆满

---

## 🔍 关键代码速查

| 功能 | 文件 | 行号 |
|------|------|------|
| Compaction 配置 Schema | `config/config.ts` | 1169-1180 |
| 环境变量覆盖 | `config/config.ts` | 250-255 |
| Compaction 开关 | `session/compaction.ts` | 35 |
| Compaction 预留值 | `session/compaction.ts` | 44 |
| Prune 开关 | `session/compaction.ts` | 61 |
| Prune 硬编码参数 | `session/compaction.ts` | 51-54 |
| 调用 Prune | `session/prompt.ts` | 723 |

---

## 💡 总结

1. **独立配置**：`auto` 控制 Compaction，`prune` 控制剪枝
2. **默认启用**：两者默认都是启用的，不需要特别配置
3. **协同工作**：Prune 日常清理，Compaction 应急压缩
4. **环境变量**：可以用 `OPENCODE_DISABLE_*` 快速禁用
5. **预留空间**：`reserved` 越大，越早触发 Compaction
