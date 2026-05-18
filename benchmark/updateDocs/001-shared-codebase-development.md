# 001 — Shared Codebase Development (场景 1: 1E / 1M / 1H)

## 变更文件

| 文件 | 变更类型 |
|------|------|
| `descriptions/1E/description.md` | 措辞修正 × 4（含 Coordination challenge 规模措辞补全） |
| `descriptions/1M/description.md` | 措辞修正 × 3 |
| `descriptions/1H/description.md` | 措辞修正 × 3 |
| `descriptions/1E/tools.json` | `can_fail` 字段修正 |
| `descriptions/1M/tools.json` | `can_fail` 字段修正 |
| `descriptions/1H/tools.json` | `can_fail` 字段修正 |
| `environments/1E/checklist.json` | `simultaneously` 措辞修正 |
| `environments/1M/checklist.json` | `simultaneously` 措辞修正 |
| `environments/1H/checklist.json` | `simultaneously` 措辞修正 |
| `tools/sim_coding.py` | `implement_code` docstring 修正；`resource_requirements()` 移除硬编码实现 |
| `tools/sim_base.py` | 新增 `load_from_metadata()`；`resource_requirements()` 升级为数据驱动 |
| `descriptions/1E/metadata.json` | **新建** — `agent_resources` + `tool_resource_map` |
| `descriptions/1M/metadata.json` | **新建** — `agent_resources` + `tool_resource_map` |
| `descriptions/1H/metadata.json` | **新建** — `agent_resources` + `tool_resource_map` |
| `environments/1E/sim.py` | 新增 `self.load_from_metadata(_METADATA)` |
| `environments/1M/sim.py` | 新增 `self.load_from_metadata(_METADATA)` |
| `environments/1H/sim.py` | 新增 `self.load_from_metadata(_METADATA)` |

---

## 变更 1：删除未使用的 `config` 模块

### 改动

| 版本 | 原文 | 改后 |
|------|------|------|
| 1E | "4 modules (auth, database, api, **config**)" | "3 modules (auth, database, api)" |
| 1M | "6 modules (auth, database, api, payment, notify, **config**)" | "5 modules (auth, database, api, payment, notify)" |
| 1H | "8 modules (auth, database, api, payment, notify, analytics, search, **config**)" | "7 modules (auth, database, api, payment, notify, analytics, search)" |

### 原因

`config` 模块在三个难度的描述中均被提及，但没有任何 agent 需要 acquire config 锁，也没有出现在 Shared Resources 列表、checklist、IR 或 sim.py 中。

这会让 LLM 产生困惑：config 是可以自由访问的公共资源？还是被遗漏了？歧义会干扰 LLM 设计协议时的资源建模。

---

## 变更 2：`"simultaneously"` → `"one at a time"`

### 改动

**Workflow 段落**（三个版本相同结构）：

```
原文：
  they must acquire locks on all modules they need to modify simultaneously,
  commit the changes, then release all locks.
  After committing, they run tests locally before finishing.

改后：
  they must acquire locks on all required modules one at a time
  (sequential acquisition), commit the changes while holding all locks,
  then release all locks.
  After committing, they run local tests — if tests fail, the developer
  reports the failure and finishes.
```

**各 agent 段落**（所有 "simultaneously" 替换为 "one at a time"）：
```
原文：acquires AUTH_MODULE and DATABASE_MODULE simultaneously
改后：acquires AUTH_MODULE and DATABASE_MODULE one at a time
```

**新增 Coordination challenge 段落**（三个版本描述规模不同）：
```
Coordination challenge: Each developer needs two module locks, and the lock
dependencies form a ring across [N] developers. Acquiring locks one at a time
can lead to circular waits if the acquisition order is not coordinated carefully.
```

### 原因（因果链）

**"simultaneously" 的歧义导致验证失效**：

`"simultaneously"` 有两种解读：
1. **原子获取**：要么同时拿到所有锁，要么一把都不拿（单个 TLA+ label 内完成）
2. **顺序获取**：逐步拿锁，提交时同时持有（多个 TLA+ label，每锁一步）

如果 LLM 按解读 1 建模（原子获取），会产生两个问题：

**问题 A — 验证不可靠（Unsoundness）**：
```
TLA+ 模型（原子）  →  TLC 验证通过  →  Runtime 执行（顺序，因为 acquire_lock API 是单锁的）
                                              ↑
                                    Runtime 可能死锁！验证结论无效
```

tracefix.runtime.monitoring 只有单锁的 `acquire_lock` API，没有多锁原子接口。TLA+ 模型的粒度必须与 runtime API 的粒度一致，否则验证对 runtime 不成立。

**问题 B — Benchmark 失去意义**：
原子获取天然打破 Coffman "持有并等待"条件，TLC 必然通过，无法区分好的协议设计（正确加锁顺序）和差的协议设计（随意加锁顺序）。场景 1 的核心挑战（Dining Philosophers）就被绕过了。

**正确的建模方式是顺序获取**，每次 `acquire_lock` 是独立的 TLA+ label。TLC 在两次 acquire 之间探索所有 interleaving，能发现循环等待死锁，验证通过代表加锁顺序设计是正确的。

---

## 变更 3：`run_local_tests` 的 `can_fail` 修正

### 改动

`descriptions/1{E,M,H}/tools.json` 中的 `run_local_tests`：

```json
原：  "can_fail": false,
      "description": "Run tests locally."

改：  "can_fail": true,
      "description": "Run tests locally. May fail if tests detect integration issues."
```

### 原因

**字段不一致**：`sim_coding.py` 中 `_DECISION_TOOLS = {"run_local_tests": 0.3}`，表示在 sim 模式下 `run_local_tests` 以 30% 概率返回失败（`success=False`）。但 `tools.json` 标注 `can_fail: false`，两者矛盾。

**缺失失败处理路径**：原描述 "they run tests locally before finishing" 没有说明测试失败时的行为，违反了 IR 设计的反模式 #3（Missing failure/recovery paths）。测试失败路径的缺失使 LLM 可能设计只有 happy path 的 IR，无法覆盖 TLC 需要验证的所有分支。

**修复方案**：
- `can_fail: true` 与 sim 行为对齐
- description 说明失败时 agent 报告失败并结束（不重试）——这是最简单的失败处理，在 IR 中对应测试节点的 either/or 分支（pass → done, fail → done with failure status），两条路径都通向终态，TLC 能完整验证

---

## 变更 4：Checklist `simultaneously` 修正（补漏）

### 改动

`environments/1{E,M,H}/checklist.json` 中的 `resource_access` 条目：

```
原：  "DEVELOPER_A acquires AUTH_MODULE and DATABASE_MODULE simultaneously to commit"
改：  "DEVELOPER_A acquires AUTH_MODULE and DATABASE_MODULE one at a time (sequential acquisition) to commit"
```

（1M/1H 同理，共 5+7 条）

### 原因

变更 2 修改了 description.md，但遗漏了 checklist.json。checklist 中的 `resource_access` 描述与 description 中的措辞相互印证，两者不一致会在评审时产生歧义。

---

## 变更 5：1E Coordination challenge 规模措辞补全

### 改动

```
原：  "the lock dependencies form a ring across developers."
改：  "the lock dependencies form a ring across all three developers."
```

### 原因

1M 和 1H 均明确写了 "all five/seven developers"，1E 遗漏了数字，不一致。

---

## 变更 6：`sim_coding.py` `implement_code` docstring 修正

### 改动

```python
原：  """Implement code. Requires holding all module locks for this agent."""
改：  """Implement code locally. No resource required."""
```

### 原因

`resource_requirements()` 方法明确只对 `commit_changes` 返回模块锁列表，`implement_code` 返回空列表。原 docstring 与实现相反，是文档错误。虽然不影响 sim 运行时行为，但会误导阅读 sim 代码的人。

---

---

## 变更 7：`metadata.json` 资源绑定声明化（数据驱动 `resource_requirements`）

### 改动

**新建文件** `descriptions/1{E,M,H}/metadata.json`，以 1E 为例：

```json
{
  "agents": ["DEVELOPER_A", "DEVELOPER_B", "DEVELOPER_C"],
  "resources": ["API_MODULE", "AUTH_MODULE", "DATABASE_MODULE"],
  "agent_resources": {
    "DEVELOPER_A": ["AUTH_MODULE", "DATABASE_MODULE"],
    "DEVELOPER_B": ["DATABASE_MODULE", "API_MODULE"],
    "DEVELOPER_C": ["API_MODULE", "AUTH_MODULE"]
  },
  "tool_resource_map": {
    "design_feature":  [],
    "implement_code":  [],
    "run_local_tests": [],
    "commit_changes":  "@agent_resources"
  }
}
```

**`tools/sim_base.py` — `SimContext` 基类**：

```python
# 构造函数新增两个字段
self._tool_resource_map: dict[str, Any] = {}
self._agent_resources: dict[str, list[str]] = {}

def load_from_metadata(self, metadata: dict) -> None:
    """从 metadata.json 加载 agent_resources 和 tool_resource_map。"""
    self._agent_resources = {k: list(v) for k, v in metadata.get("agent_resources", {}).items()}
    self._tool_resource_map = dict(metadata.get("tool_resource_map", {}))

def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
    """数据驱动查询：静态列表 or "@agent_resources" 动态映射。"""
    if not self._tool_resource_map:
        return []
    mapping = self._tool_resource_map.get(tool_name)
    if mapping is None:
        return []
    if mapping == "@agent_resources":
        agent_id = kwargs.get("agent_id", "")
        return list(self._agent_resources.get(agent_id, []))
    if isinstance(mapping, list):
        return list(mapping)
    return []
```

**`tools/sim_coding.py` — `CodingSim`**：

```python
# 删除原先硬编码的 resource_requirements() 覆盖方法，改用注释说明
# resource_requirements() is handled by SimContext.load_from_metadata()
# via metadata.json tool_resource_map / agent_resources.

# commit_changes 回退逻辑：优先 metadata-driven，兜底 constructor 参数
modules = (self._agent_resources.get(agent_id)
           or self._agent_modules.get(agent_id, []))
```

**`environments/1{E,M,H}/sim.py`** — 在构造函数末尾加载 metadata：

```python
_METADATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent
     / "descriptions" / "1E" / "metadata.json").read_text()
)

class SharedCodebaseSim(CodingSim):
    def __init__(self) -> None:
        super().__init__(...)
        self.load_from_metadata(_METADATA)   # ← 新增
```

### 原因

**原有问题：资源绑定硬编码在 Python 子类中**

变更前，`CodingSim` 子类通过覆盖 `resource_requirements()` 方法来声明哪些工具需要哪些资源：

```python
# 旧写法（sim_coding.py 内曾存在）
def resource_requirements(self, tool_name: str, **kwargs: Any) -> list[str]:
    agent_id = kwargs.get("agent_id", "")
    if tool_name == "commit_changes":
        return self._agent_modules.get(agent_id, [])
    if tool_name == "implement_code":
        return self._agent_modules.get(agent_id, [])
    return []
```

这有三个问题：

1. **数据分散在代码中**：资源绑定逻辑隐藏在 Python 方法体内，无法在不读代码的情况下了解"哪个工具需要哪些资源"。
2. **每个新场景都要覆盖该方法**：未来添加场景 2~16 时，每个 sim 子类都需重新实现同样的逻辑（开闭原则违反）。
3. **与 `tools.json` 语义割裂**：`tools.json` 中已有 `can_fail`、`description` 等元数据字段，资源绑定却在另一处，造成信息分散。

**解决方案：声明式 `metadata.json` + 基类通用实现**

把"哪个 agent 拥有哪些资源"（`agent_resources`）和"哪个 tool 需要哪些资源"（`tool_resource_map`）从 Python 代码中提取到 JSON 文件，基类 `SimContext.load_from_metadata()` 负责加载，`resource_requirements()` 通用实现根据 JSON 配置作答。

`"@agent_resources"` 是动态哨兵值，表示"按调用 agent 查询其 `agent_resources` 列表"——这解决了 `commit_changes` 这类每个 agent 所需资源不同的场景，同时保持 JSON 纯声明式（无需 Python 代码）。

**设计取舍：为何不把资源绑定并入 `tools.json`？**

`tools.json` 定义工具的接口（参数 schema、`can_fail` 标志），面向 LLM prompt 生成，不应包含 sim 运行时实现细节（哪个 agent 拿哪些资源）。`metadata.json` 是 sim 层的配置文件，与验证/prompt 层正交，独立管理符合单一职责原则。

---

## 未修改项（设计取舍）

**难度区分方式**（E/M/H 是同一问题的规模扩展）

三个难度级别都是相同的 Dining Philosophers 问题，只是环的大小不同（3→5→7 节点）。理论上协调逻辑的设计难度相同，难度差异主要体现在 TLC 状态空间大小和 agent 数量。

保持现状的理由：场景 1 定位是"纯锁协调"的基础测试，清晰的规模梯度便于分析 TLC 验证时间和 LLM 在不同规模下的表现，不需要引入额外的协调复杂度。
