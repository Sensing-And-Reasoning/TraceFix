# Benchmark Fix Patterns

本文档记录对 benchmark 场景进行质量检查时发现的 **可复用修复模式**，每个 pattern 附有问题根因、检测方法和修复步骤。首次从场景 1 (1E/1M/1H) 的修复工作中提炼，适用于所有场景。

---

## Pattern 1 — `_test_done` 提前设置 Bug

### 问题根因

`run_local_tests`（或同类决策工具）在调用 `should_fail()` 之前就将 `_test_done[key] = True`，导致 `is_complete()` 在测试失败时仍返回 `True`。

```python
# ❌ 错误：提前标记完成
def run_local_tests(self, agent_id: str, **kwargs):
    key = self._match_key(self._test_done, agent_id, feature)
    self._test_done[key] = True          # ← 在 should_fail() 之前！
    if self.should_fail("run_local_tests", agent_id):
        return ToolResult(..., success=False)
    return ToolResult(..., success=True)
```

### 影响

- `--scenario N` 和 `--difficulty K` 注入失败后，sim 的 `is_complete()` 仍返回 `True`
- 运行结果显示 `Complete: True`，掩盖了实际的协调失败

### 检测方法

在 sim 类的决策工具方法中搜索完成标志赋值语句，检查其位置是否在 `should_fail()` 之前：

```python
# 检查是否存在此类模式
key = ...
self._xxx_done[key] = True     # ← 如果在 should_fail() 前 = bug
if self.should_fail(...):
    return ToolResult(..., success=False)
```

### 修复

将完成标志的赋值移到成功路径内（`should_fail()` 返回 `False` 之后）：

```python
# ✅ 正确：仅在成功时标记
def run_local_tests(self, agent_id: str, **kwargs):
    key = self._match_key(self._test_done, agent_id, feature)
    if self.should_fail("run_local_tests", agent_id):
        return ToolResult(..., success=False)    # 不设置 _test_done
    if key in self._test_done:
        self._test_done[key] = True              # ← 仅成功时设置
    return ToolResult(..., success=True)
```

### 适用范围

所有使用完成标志（`_test_done`、`_commit_done`、`_xxx_done`）且工具可能失败的 sim 子类。

---

## Pattern 2 — 无重试分支子类的 `_DECISION_TOOLS` 覆盖

### 问题根因

`CodingSim`（或其他基类）通过类变量 `_DECISION_TOOLS` 声明哪些工具参与故障注入。所有子类共享此变量。当子类的协议中**没有重试循环**（测试结果是终态，无论通过还是失败都直接结束），`--scenario N` 仍然会触发故障注入，使完成标志永远无法设为 `True`，`is_complete()` 永远返回 `False`。

### 影响

```
--scenario 2 + 1E（无重试）→ run_local_tests 失败 → _test_done 不设置
                              → is_complete() = False（永久）
                              → 运行完 max_rounds 显示 Complete: False
                              → 即使 agent 实际上完全正确地执行了协议也被判失败
```

### 检测方法

对照 PlusCal 协议（`states.json` / `Protocol.tla`）检查每个测试节点的后继状态：

- 若测试节点的所有分支（pass/fail）都通向 `__done__`，则该子类**无重试**
- 若测试节点的 fail 分支指回实现/提交步骤，则该子类**有重试**

有重试的子类可正常继承 `_DECISION_TOOLS`；无重试的子类必须覆盖为 `{}`。

### 修复

在无重试的 sim 子类中显式覆盖：

```python
class SharedCodebaseSim(CodingSim):
    """1E: Three developers — terminal tests (no retry).

    Tests are terminal (pass or fail, no retry), so run_local_tests is not
    a decision tool — failure injection via --scenario/--difficulty is disabled.
    """

    # No retry loop: test outcome is terminal regardless.
    # Overriding to empty prevents --scenario/--difficulty from injecting
    # failures that would leave _test_done permanently False.
    _DECISION_TOOLS: dict = {}
```

### 适用范围

所有 sim 子类，凡是协议中存在终态测试（无重试）的都需要检查并覆盖。典型模式：
- E（Easy）和 M（Medium）难度：终态测试，需要覆盖
- H（Hard）难度：有重试循环，继承基类 `_DECISION_TOOLS`

---

## Pattern 3 — sim.py Feature Name 与 Tools 对齐

### 问题根因

`sim.py` 中 `DesignStep`、`ImplementStep`、`TestStep` 的 `feature` 参数使用了缩写名（如 `user_auth`），而 description.md、tools.json 和 agent prompt 使用全称（`user_authentication`）。虽然 `_match_key` 有 prefix 模糊匹配，但不同的名称造成可读性问题和潜在的匹配失效风险。

### 检测方法

对比以下三处的 feature 名称：
1. `sim.py` 的 `DesignStep` / `ImplementStep` / `TestStep`
2. `descriptions/{id}/description.md` 中各 agent 负责的功能名
3. `descriptions/{id}/tools.json` 中工具的 `description` 字段

若存在缩写差异（`user_auth` vs `user_authentication`），需对齐。

### 修复

统一使用 description.md 和 tools.json 中的全称作为标准：

```python
# ❌ 缩写名（旧）
DesignStep(agent_id="DEVELOPER_A", feature="user_auth")

# ✅ 全称（新）
DesignStep(agent_id="DEVELOPER_A", feature="user_authentication")
```

### 适用范围

所有使用 `DesignStep`/`ImplementStep`/`TestStep` 的 coding sim 子类。

---

## Pattern 4 — CommitStep 和 metadata.json 模块列表排序

### 问题根因

`CommitStep(modules=[...])` 和 `metadata.json` 中 `agent_resources` 的模块列表顺序不一致（有时按添加顺序，有时按字母顺序），导致代码可读性差，diff 难以审查。

**注意**：排序仅用于 sim 内部配置，**不影响** description.md 中向 agent 展示的锁获取顺序（description.md 的顺序是挑战本身，见 Pattern 5）。

### 修复

统一使用字母顺序：

```python
# ❌ 非字母顺序（旧）
CommitStep(agent_id="DEVELOPER_B", modules=["DATABASE_MODULE", "API_MODULE"])

# ✅ 字母顺序（新）
CommitStep(agent_id="DEVELOPER_B", modules=["API_MODULE", "DATABASE_MODULE"])
```

```json
// metadata.json agent_resources
"DEVELOPER_B": ["API_MODULE", "DATABASE_MODULE"]  // 字母顺序
```

### 适用范围

所有 coding sim 子类的 `CommitStep` 列表和 `metadata.json`。

---

## Pattern 5 — Description 不泄露解法（保留挑战、隐藏答案）

### 问题根因

description.md 中若出现以下任何内容，等于直接告诉 agent 解题答案：

1. 明确写出"按字母顺序获取锁"（正确加锁顺序 = 挑战的答案）
2. 写出 "(exclusive access)" 标注（虽不致命，但暗示需要独占锁）
3. 写出"等待锁时可继续做本地工作"（与 `acquire_lock` 阻塞式 API 矛盾）
4. 明确列出协调挑战的解决方案（如 Dining Philosophers 的死锁解法）

**关键区分**：description.md 中各 agent 的模块列表**顺序**（如 B: `DATABASE_MODULE` 和 `API_MODULE`）可以保留原始的"环形顺序"——这正是会导致死锁的顺序，是**挑战本身**，不是答案。

### 检测方法

阅读 description.md，用以下问题自检：
- 如果 agent 完全按照 description 的提示来实现协议，它会选择正确的加锁顺序吗？
  - 如果"是"→ description 泄露了解法
  - 如果"不一定"→ description 保留了挑战性

### 修复原则

| 内容 | 处理方式 |
|------|---------|
| 显式锁获取顺序（字母序） | 删除 |
| Shared Resources 列表 | 保留（agent 需要知道有哪些资源） |
| "(exclusive access)" 标注 | 删除 |
| "等待锁期间可继续工作" | 删除（与 blocking API 矛盾） |
| 各 agent 的模块列表（环形顺序） | 保留（这是挑战，不是答案） |
| 测试失败后的行为描述 | 保留（需说明重试或终止） |

**description 改写示例：**

```markdown
# ❌ 泄露解法（旧）
- DEVELOPER_A: Building user authentication. Acquires AUTH_MODULE and
  DATABASE_MODULE **in alphabetical order** to avoid circular waits.

# ✅ 保留挑战（新）
- **DEVELOPER_A**: Building user authentication. Needs to modify
  **AUTH_MODULE** and **DATABASE_MODULE**.
```

```markdown
# ❌ 多余暗示
## Shared Resources
- **AUTH_MODULE**: Authentication module (exclusive access)

# ✅ 干净
## Shared Resources
- **AUTH_MODULE**: Authentication module
```

### 适用范围

所有涉及锁协调的场景（尤其是存在 Dining Philosophers / 资源环形依赖的场景）。

---

## Pattern 6 — sim_coding.py（或其他 sim 基类）Docstring 准确性

### 问题根因

sim 基类的工具 docstring 可能声称某工具"需要持有资源锁"，但实际 `resource_requirements()` 返回空列表——即该工具并不需要锁。

```python
# ❌ 错误的 docstring
def implement_code(self, agent_id: str, **kwargs):
    """Implement code. Requires holding all module locks for this agent."""  # 错！

# ✅ 正确
def implement_code(self, agent_id: str, **kwargs):
    """Implement code locally. No resource required."""
```

### 检测方法

对照 `metadata.json` 的 `tool_resource_map` 检查每个工具的 docstring：

```json
"tool_resource_map": {
    "design_feature":  [],      // 无锁
    "implement_code":  [],      // 无锁  ← docstring 必须说"No resource required"
    "run_local_tests": [],      // 无锁
    "commit_changes":  "@agent_resources"   // 需要锁
}
```

### 适用范围

所有 sim 类的工具方法。每次修改 `tool_resource_map` 后需同步检查对应方法的 docstring。

---

## 快速检查清单（新增或修改场景时使用）

在提交对任何场景的修改前，逐项确认：

```
[ ] sim.py：完成标志赋值在 should_fail() 之后（Pattern 1）
[ ] sim.py：无重试协议的子类已覆盖 _DECISION_TOOLS = {}（Pattern 2）
[ ] sim.py：feature 名称与 description.md / tools.json 一致（Pattern 3）
[ ] sim.py CommitStep 和 metadata.json：模块列表按字母排序（Pattern 4）
[ ] description.md：不包含显式锁顺序/解法提示（Pattern 5）
[ ] description.md：Shared Resources 无 "(exclusive access)" 标注（Pattern 5）
[ ] description.md：无与工具 API 矛盾的描述（Pattern 5）
[ ] sim 基类工具方法的 docstring 与 tool_resource_map 一致（Pattern 6）
[ ] _test_done / _commit_done 等完成标志：仅在成功路径设置（Pattern 1）
[ ] 有重试分支的 sim 子类：在 states.json 中确认 fail → retry 的后继状态（Pattern 2）
```

---

## 来源记录

| Pattern | 首次发现场景 | 修复 commit |
|---------|------------|------------|
| Pattern 1 | 1H (retry loop) | update/tla-agent-skill |
| Pattern 2 | 1E / 1M (terminal tests) | update/tla-agent-skill |
| Pattern 3 | 1H / 1E / 1M | update/tla-agent-skill |
| Pattern 4 | 1H / 1E / 1M | update/tla-agent-skill |
| Pattern 5 | 1H / 1E / 1M | update/tla-agent-skill |
| Pattern 6 | 1H (sim_coding.py) | update/tla-agent-skill |
