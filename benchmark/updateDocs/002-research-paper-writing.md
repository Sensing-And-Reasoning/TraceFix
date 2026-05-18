# 002 — Research Paper Writing (场景 2: 2E / 2M / 2H)

## 变更文件

| 文件 | 变更类型 |
|------|------|
| `descriptions/2E/description.md` | 措辞修正 × 3 + 结构修正 |
| `descriptions/2M/description.md` | 措辞修正 × 3 + 结构修正 |
| `descriptions/2H/description.md` | 措辞修正 × 3 + 结构修正 |
| `descriptions/2E/tools.json` | `can_fail` 字段修正 |
| `descriptions/2M/tools.json` | `can_fail` 字段修正 |
| `descriptions/2H/tools.json` | `can_fail` 字段修正 |
| `environments/2E/checklist.json` | `simultaneously` 措辞修正 |
| `environments/2M/checklist.json` | `simultaneously` 措辞修正 |
| `environments/2H/checklist.json` | `simultaneously` 措辞修正 |

---

## 变更 1：删除未使用的 section

### 改动

| 版本 | 原文 | 改后 |
|------|------|------|
| 2E | "4 sections (intro, methods, results, **discussion**)" | "3 sections (intro, methods, results)" |
| 2M | "6 sections (intro, background, methods, experiments, results, **conclusion**)" | "5 sections (intro, background, methods, experiments, results)" |
| 2H | "8 sections (intro, background, related work, methods, experiments, results, discussion, **conclusion**)" | "7 sections (intro, background, related work, methods, experiments, results, discussion)" |

### 原因

与场景 1 的 `config` 模块问题相同。

每个版本的标题中多列出了一个 section（2E 的 DISCUSSION、2M/2H 的 CONCLUSION），但该 section 从未出现在：
- Shared Resources 列表中
- 任何 agent 的锁需求里
- sim.py 的 `_WRITE_STEPS` 中
- checklist.json 中

环形拓扑完全由 N 个 agent 和 N 个 section 构成（2E: 3+3, 2M: 5+5, 2H: 7+7）。多出的 section 只产生歧义：这个 section 是可以自由访问的？还是被遗漏了？

---

## 变更 2：`"simultaneously"` → `"one at a time"`

### 改动

**Workflow 段落**（三个版本）：

```
原文：
  they must acquire locks on all sections they need to edit simultaneously
  to maintain cross-section consistency, write the content, then release all locks.
  After writing, they review their own work locally before finishing.

改后：
  they must acquire locks on all required sections one at a time
  (sequential acquisition), write the content while holding all locks,
  then release all locks. After writing, they review their own work locally —
  if the review finds issues, the researcher reports the finding and finishes.
```

**各 agent 段落**（所有 "simultaneously" 替换为 "one at a time"）：
```
原文：needs to edit both INTRO_SECTION and METHODS_SECTION simultaneously
改后：needs to edit both INTRO_SECTION and METHODS_SECTION one at a time
```

**新增 Coordination challenge 段落**（三个版本描述规模不同）：
```
Coordination challenge: Each researcher needs two section locks, and the lock
dependencies form a ring across [N] researchers. Acquiring locks one at a time
can lead to circular waits if the acquisition order is not coordinated carefully.
```

**checklist.json** 中的 `resource_access` 描述也同步更新：
```
原文：RESEARCHER_A acquires INTRO_SECTION and METHODS_SECTION simultaneously
改后：RESEARCHER_A acquires INTRO_SECTION and METHODS_SECTION one at a time (sequential acquisition)
```

### 原因

与场景 1 完全相同（详见 `001-shared-codebase-development.md`，变更 2）：

1. `"simultaneously"` 的原子解读会让 LLM 用单个 TLA+ label 获取两把锁，规避 Coffman 持有并等待条件，使 TLC 对任意加锁顺序都能通过验证 → benchmark 失去意义。
2. tracefix.runtime.monitoring 的 `acquire_lock` API 是单锁的，TLA+ 模型必须与 API 粒度一致，否则验证对 runtime 不成立。
3. 正确建模：顺序获取，每次 `acquire_lock` 是独立 TLA+ label，TLC 能探索两次 acquire 之间的所有 interleaving，发现循环等待死锁。

场景 2 与场景 1 在结构上完全相同（Dining Philosophers 问题，只是领域背景不同：研究员写论文 vs 开发者提交代码）。

---

## 变更 3：`review_own_work` 的 `can_fail` 修正

### 改动

`descriptions/2{E,M,H}/tools.json` 中的 `review_own_work`：

```json
原：  "can_fail": false,
      "description": "Review own written work."

改：  "can_fail": true,
      "description": "Review own written work. May find issues requiring revision."
```

### 原因

与场景 1 的 `run_local_tests` 修正相同：

**字段不一致**：`sim_smart_building.py` 中 `_DECISION_TOOLS = {"review_own_work": 0.3}`，表示在 sim 模式下 `review_own_work` 以 30% 概率返回失败（`success=False`，状态为 `needs_revision`）。但 `tools.json` 标注 `can_fail: false`，两者矛盾。

**缺失失败处理路径**：原描述 "they review their own work locally before finishing" 没有说明审阅失败时的行为，违反 IR 设计反模式 #3（Missing failure/recovery paths）。修复后，失败路径明确：审阅发现问题 → 研究员报告发现并结束（不重试）。

---

## 未修改项（第一轮，设计取舍）

场景 2 是场景 1 的等价结构（Dining Philosophers），只是领域背景和锁名称不同。两个场景的差异完全来自背景叙事，不影响协调难度，也不需要引入额外的协调复杂度。

保持现状理由：场景 1 和 2 的并存提供了"同一问题、不同领域"的对照组，可以测试 LLM 是否能在不同背景下识别出相同的结构性协调挑战（Dining Philosophers）。

---

## 第二轮修复（fixpattern.md 应用）

应用 `benchmark/updateDocs/fixpattern.md` 中的 Pattern 1–6 进行系统性修复。

### 变更文件（第二轮）

| 文件 | Pattern | 变更类型 |
|------|---------|---------|
| `tools/sim_smart_building.py` | P1 + P6 | `review_own_work` 完成标志移到成功路径；`write_to_document` docstring 修正 |
| `environments/2E/sim.py` | P2 + P4 + P6 | `_DECISION_TOOLS={}` 覆盖；WriteStep 字母顺序；节数 "4" → "3" |
| `environments/2M/sim.py` | P2 + P4 + P6 | `_DECISION_TOOLS={}` 覆盖；WriteStep 字母顺序；节数 "6" → "5" |
| `environments/2H/sim.py` | P2 + P4 + P6 | `_DECISION_TOOLS={}` 覆盖；WriteStep 字母顺序；节数 "8" → "7" |
| `environments/2E/checklist.json` | P4 | RA3 字母顺序 |
| `environments/2M/checklist.json` | P4 | RA1/RA3/RA5 字母顺序 |
| `environments/2H/checklist.json` | P4 | RA1/RA3/RA4/RA6 字母顺序 |
| `descriptions/2E/description.md` | P5 | 完整重写：移除 `(exclusive access)`、"While waiting..." 句、"Coordination challenge..." 段 |
| `descriptions/2M/description.md` | P5 | 同上 |
| `descriptions/2H/description.md` | P5 | 同上 |

---

### 变更 4：`sim_smart_building.py` — `review_own_work` 提前完成 Bug (Pattern 1)

#### 改动

```python
# ❌ 旧（_review_done 在 should_fail() 之前设置）
key = self._match_key(self._review_done, agent_id, section)
if key in self._review_done:
    self._review_done[key] = True         # ← 提前标记！
if self.should_fail("review_own_work", agent_id):
    return ToolResult(..., success=False)

# ✅ 新（仅在成功时标记）
if self.should_fail("review_own_work", agent_id):
    return ToolResult(..., success=False)  # ← 不设置 _review_done
# Only mark done when review actually passes
key = self._match_key(self._review_done, agent_id, section)
if key in self._review_done:
    self._review_done[key] = True
```

#### 原因

与 `sim_coding.py` 的 `run_local_tests` bug 完全相同：`_review_done[key] = True` 在 `should_fail()` 之前设置，导致审阅失败时 `is_complete()` 仍返回 `True`。`--scenario N` 或 `--difficulty K` 参数注入失败后，表现为 Complete:True（完全掩盖了失败）。

---

### 变更 5：`environments/2{E,M,H}/sim.py` — `_DECISION_TOOLS` 覆盖 (Pattern 2)

#### 改动

三个 `ResearchPaperSim` 子类新增：

```python
# No retry loop: review outcome is terminal regardless.
# Overriding to empty prevents --scenario/--difficulty from injecting
# failures that would leave _review_done permanently False.
_DECISION_TOOLS: dict = {}
```

#### 原因

三个任务的 Workflow 均描述：审阅失败 → "reports the finding and **finishes**"（终态，无重试）。但三个子类都从 `SmartBuildingSim` 继承了 `_DECISION_TOOLS = {"review_own_work": 0.3}`。在修复 Pattern 1（_review_done 不再提前设置）后，`--scenario N` 会使 `review_own_work` 在无重试场景中永久失败，`_review_done` 永远不设为 True，`is_complete()` 永远返回 False。

---

### 变更 6：sim.py docstring 节数修正 (Pattern 6)

| 版本 | 原文 | 改后 |
|------|------|------|
| 2E | "co-authoring a paper with **4** sections" | "co-authoring a paper with **3** sections" |
| 2M | "co-authoring a paper with **6** sections" | "co-authoring a paper with **5** sections" |
| 2H | "co-authoring a paper with **8** sections" | "co-authoring a paper with **7** sections" |

各版本均比实际 section 数多 1，是文档错误。

---

### 变更 7：WriteStep 和 checklist.json 字母顺序 (Pattern 4)

#### WriteStep 改动（字母顺序，`_write_steps` 的 key 已经 sorted，顺序不影响匹配但要统一）

| Agent | 旧（环形顺序） | 新（字母顺序） |
|-------|-------------|-------------|
| 2E-C | `[RESULTS, INTRO]` | `[INTRO, RESULTS]` |
| 2M-A | `[INTRO, BACKGROUND]` | `[BACKGROUND, INTRO]` |
| 2M-C | `[METHODS, EXPERIMENTS]` | `[EXPERIMENTS, METHODS]` |
| 2M-E | `[RESULTS, INTRO]` | `[INTRO, RESULTS]` |
| 2H-A | `[INTRO, BACKGROUND]` | `[BACKGROUND, INTRO]` |
| 2H-C | `[RELATED, METHODS]` | `[METHODS, RELATED]` |
| 2H-D | `[METHODS, EXPERIMENTS]` | `[EXPERIMENTS, METHODS]` |
| 2H-F | `[RESULTS, DISCUSSION]` | `[DISCUSSION, RESULTS]` |

#### checklist.json resource_access 同步更新（字母顺序，与 sim.py 一致）

---

### 变更 8：description.md 完整重写 (Pattern 5)

三处删除：

1. **`(exclusive access)` 标注** — Shared Resources 列表中每个资源后面的标注删除
2. **"While waiting for section locks, a researcher can continue doing literature review and local drafting."** — 与 `acquire_lock` 阻塞式 API 矛盾的句子删除
3. **"Coordination challenge: Each researcher needs two section locks, and the lock dependencies form a ring..."** — 过度提示段落删除（与场景 1 保持一致）

**保留（设计取舍）**：
- 各 agent 段落的**环形顺序**（如 RESEARCHER_C: "RESULTS_SECTION and INTRO_SECTION"）— 这是挑战，不是答案
- Shared Resources 列表本身 — agent 需要知道有哪些资源
- 测试失败行为描述（"reports the finding and finishes"）— 明确终态语义是必要的
