# TodoWrite Prompt 深度解析：AI 任务管理的艺术

> 文件路径：`packages/opencode/src/tool/todowrite.txt`
>
> 167 行精心设计的 Prompt，堪称"AI 项目经理培训手册"。

---

## 🎭 核心比喻：餐厅主厨的任务板

想象你是一家**高级餐厅的主厨**（AI Agent），厨房里挂着一块**磁性任务板**。

| Prompt 概念 | 餐厅比喻 |
|------------|---------|
| TodoWrite Tool | 磁性任务板和马克笔 |
| Todo 状态 | 不同颜色的磁贴 |
| pending | 🔵 蓝色：待准备 |
| in_progress | 🟡 黄色：正在烹饪 |
| completed | 🟢 绿色：已出菜 |
| cancelled | 🔴 红色：取消 |
| Prompt 规则 | 厨房操作手册 |

---

## 📋 结构解剖：三层递进式教学

```
┌─────────────────────────────────────────────────────────────┐
│  第一层：原则定义（第 1-23 行）                               │
│  "是什么" + "什么时候用" + "什么时候不用"                      │
├─────────────────────────────────────────────────────────────┤
│  第二层：正反示例（第 25-144 行）                             │
│  4 个"要用"的例子 + 4 个"不要用"的例子                        │
│  每个例子都带 <reasoning> 解释原因                            │
├─────────────────────────────────────────────────────────────┤
│  第三层：操作规范（第 146-167 行）                            │
│  状态定义 + 管理规则 + 最佳实践                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔥 第一层：决策边界（黄金法则）

### 使用时机（7 条规则）

```markdown
1. Complex multistep tasks - 3+ 步骤
2. Non-trivial and complex tasks - 需要仔细规划
3. User explicitly requests todo list - 用户明确要求
4. User provides multiple tasks - 多个任务（逗号分隔）
5. After receiving new instructions - 收到新指令立即记录
6. After completing a task - 完成后标记并添加后续任务
7. When you start working on a new task - 标记为 in_progress
```

**核心逻辑**：
> **3 步以上** 或 **用户明确列表** → 开任务板

### 不使用时机（4 条规则）

```markdown
1. Single, straightforward task - 单一简单任务
2. Task is trivial - 追踪它没组织收益
3. Less than 3 trivial steps - < 3 个琐碎步骤
4. Purely conversational - 纯对话/信息性
```

**关键警告**（第 23 行）：
```markdown
NOTE that you should not use this tool if there is only one trivial task to do. 
In this case you are better off just doing the task directly.
```

> 🎯 **不要为小事开会！直接干！**

---

## 💎 第二层：示例教学（Prompt Engineering 典范）

这是整个文件最精彩的部分——**用 8 个详细例子教 AI 何时开任务板**。

### 正例 1：暗黑模式（功能开发）

```
用户: "加暗黑模式切换，还要跑测试和构建"
        ↓
任务板:
  1. 创建暗黑模式组件
  2. 添加状态管理
  3. 实现 CSS 样式
  4. 更新现有组件
  5. 运行测试和构建
```

**<reasoning> 要点**：
- 多步骤功能
- 用户明确要求测试和构建
- 助手推断出需要验证步骤

### 正例 2：重命名函数（代码重构）

```
用户: "把 getCwd 重命名为 getCurrentWorkingDirectory"
        ↓
助手: 先搜索代码库...
        ↓
发现: 15 个实例，8 个文件
        ↓
任务板: 为每个文件创建更新任务
```

**<reasoning> 要点**：
- 先探索了解范围
- 发现涉及多文件 → 复杂任务
- 系统化跟踪确保不遗漏

### 正例 3：电商功能（多模块开发）

```
用户: "实现这些功能：用户注册、商品目录、购物车、结账流程"
        ↓
任务板:
  - 用户注册（数据库模型、API、前端表单）
  - 商品目录（...）
  - 购物车（...）
  - 结账流程（...）
```

**<reasoning> 要点**：
- 逗号分隔的多个复杂功能
- 拆分成可管理的子任务
- 跟踪整个实现进度

### 正例 4：性能优化（分析后规划）

```
用户: "优化 React 应用，渲染很慢"
        ↓
助手: 先分析代码库...
        ↓
发现多个问题:
  - ProductList 重复计算
  - Dashboard 长列表无虚拟化
  - Gallery 图片加载慢
  - ShoppingCart 状态循环
  - 包体积过大
        ↓
任务板: 每个问题一个任务
```

**<reasoning> 要点**：
- 先检查代码识别具体问题
- 性能优化是多步骤非平凡任务
- 系统化跟踪确保所有瓶颈解决

---

### 反例 1：Hello World（太简单）

```
用户: "Python 怎么打印 Hello World?"
        ↓
❌ 不开任务板
        ↓
直接回答: print("Hello World")
```

**<reasoning>**: 单一步骤，无需跟踪

### 反例 2：git status 解释（纯信息）

```
用户: "git status 是干什么的?"
        ↓
❌ 不开任务板
        ↓
直接解释命令作用
```

**<reasoning>**: 信息性请求，无实际编码任务

### 反例 3：添加注释（单点修改）

```
用户: "给 calculateTotal 函数加个注释"
        ↓
❌ 不开任务板
        ↓
直接用 Edit 工具添加
```

**<reasoning>**: 单一位置简单修改，无需多步骤

### 反例 4：npm install（单命令）

```
用户: "运行 npm install 告诉我结果"
        ↓
❌ 不开任务板
        ↓
直接执行命令
```

**<reasoning>**: 单一命令执行，立即出结果

---

## ⚙️ 第三层：状态机与管理哲学

### 四种状态（颜色磁贴）

| 状态 | 含义 | 餐厅比喻 |
|------|------|---------|
| `pending` | 还没开始 | 🔵 食材还没切 |
| `in_progress` | 正在做 | 🟡 正在锅里炒 |
| `completed` | 已完成 | 🟢 已出菜上桌 |
| `cancelled` | 取消了 | 🔴 客人不要了 |

### 核心管理规则（厨房纪律）

```markdown
1. Update task status in real-time - 实时更新状态
2. Mark complete IMMEDIATELY after finishing - 完成立即标记（不要批量）
3. Only have ONE task in_progress at any time - 一次只做一道菜！
4. Complete current tasks before starting new ones - 做完这锅再炒下一锅
5. Cancel tasks that become irrelevant - 取消无用任务
```

**关键洞察**：
> 第 3 条规则 **"一次只有一个 in_progress"** 强制**串行专注**，避免 AI "多头并进"导致混乱！

### 任务拆分原则

```markdown
- Create specific, actionable items - 具体可执行
- Break complex tasks into smaller steps - 拆分复杂任务
- Use clear, descriptive task names - 清晰描述
```

---

## 🎓 Prompt Engineering 技巧总结

### 技巧 1：量化触发条件

```markdown
❌ "复杂任务时用"
✅ "3 步以上时用" / "less than 3 trivial steps 不用"
```

### 技巧 2：正反对比教学

4 个正例 + 4 个反例，覆盖各种场景：
- 功能开发、代码重构、多模块、性能优化
- 简单问答、信息解释、单点修改、单命令

### 技巧 3：示例内嵌推理

```markdown
<example>
  [对话示例]
  <reasoning>
    1. 因为 X
    2. 所以 Y
    3. 因此用任务板
  </reasoning>
</example>
```

**Why it works**: 不仅告诉模型"做了什么"，还告诉"为什么这么做"，培养**决策能力**而非**死记硬背**。

### 技巧 4：强制行为规则

```markdown
- "limit to ONE task at a time" （强制单任务）
- "IMMEDIATELY after finishing" （强制及时更新）
- "don't batch completions" （强制不拖延）
```

### 技巧 5：兜底条款

```markdown
"When in doubt, use this tool."
```

> 不确定？开任务板！宁可过度规划，不要遗漏跟踪。

---

## 🎬 一句话总结

> **这份 167 行的 Prompt 是"AI 项目经理的培训手册"——通过量化规则（3 步原则）、正反示例（8 个场景）、状态机（4 状态）和强制纪律（单任务专注），教会 AI 何时该郑重其事地规划任务，何时该直接动手干活，最终成为有条不紊的工程助手！** 🎯

---

*分析完成时间：2026-03-16*
*分析者：Kimi Code*
