# IMPLEMENTATION SPEC — Day 08 LangGraph Agent Lab

> Ngôn ngữ: Tiếng Việt. Thuật ngữ kỹ thuật giữ nguyên tiếng Anh.
> Mục tiêu: 100 điểm + 5 bonus extension. Hệ thống robust, có đầy đủ fallback, chạy ổn định.

---

## 1. Tổng quan Lab

**Bài toán**: Xây dựng support-ticket agent dùng LangGraph — nhận ticket từ người dùng, phân loại, xử lý theo route phù hợp, có retry loop, human-in-the-loop approval, persistence, và metrics.

**Tech stack**:
- `langgraph >= 0.3.0` — graph execution engine
- `pydantic >= 2.7` — state schema & validation
- `langgraph-checkpoint-sqlite` — SQLite persistence
- `streamlit` — HITL approval UI
- `typer` — CLI
- `ruff` / `mypy` — lint & type check

**Constraint quan trọng**: KHÔNG hardcode câu trả lời cho từng scenario. Graph phải route dựa trên keyword logic và state, vì grader dùng hidden scenarios khác.

---

## 2. Tiêu chí chấm điểm

| Hạng mục | Điểm | Tiêu chí cụ thể |
|---|---:|---|
| Architecture & state schema | 20 | Typed state, `Annotated[list, add]` reducers, serializable, node boundaries rõ |
| Graph behavior | 25 | 7 scenarios đúng route, retry có bound, HITL path, mọi path kết thúc |
| Persistence & recovery | 15 | Checkpointer wire, `thread_id` per run, state history hoặc crash-resume |
| Metrics & tests | 20 | `metrics.json` valid, ≥6 scenarios, tests pass, `latency_ms` > 0 |
| Report & demo | 15 | Architecture explanation, metrics table, failure analysis, improvement plan |
| Production hygiene | 5 | Lint pass, type pass, config qua YAML, env handling |

**Band 90–100**: Core + metrics + report + ≥1 extension.
**Mục tiêu**: 100 điểm + 5 extension.

---

## 3. Phân tích hiện trạng

### 3.1 Đã hoàn chỉnh (không cần sửa)
| File | Trạng thái |
|---|---|
| `state.py` | Hoàn chỉnh — schema, reducers, `initial_state()` |
| `graph.py` | Hoàn chỉnh — wiring đầy đủ (cần mở rộng cho parallel fan-out) |
| `metrics.py` | Hoàn chỉnh — schema + helpers |
| `cli.py` | Cơ bản hoàn chỉnh — cần thêm `latency_ms` |
| `scenarios.py` | Hoàn chỉnh |
| `tests/test_state.py` | Hoàn chỉnh |

### 3.2 Cần fix (bugs / incomplete)

**`nodes.py` — `classify_node` thiếu keywords:**
```python
# Hiện tại chỉ có:
risky: "refund", "delete", "send"
tool:  "status", "order", "lookup"
error: "timeout", "fail"

# Cần thêm:
risky: + "cancel", "remove", "revoke"
tool:  + "check", "track", "find", "search"
error: + "error", "crash", "unavailable"
```

**`persistence.py` — API cũ sẽ crash khi dùng SQLite:**
```python
# Sai (API cũ, trả về context manager):
SqliteSaver.from_conn_string(database_url)

# Đúng:
import sqlite3
conn = sqlite3.connect(database_url, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
SqliteSaver(conn=conn)
```

**`cli.py` — `latency_ms` luôn = 0:**
```python
# Cần đo thời gian trong run_scenarios():
import time
start = time.perf_counter()
final_state = graph.invoke(state, config=run_config)
latency_ms = int((time.perf_counter() - start) * 1000)
# Truyền latency_ms vào metric_from_state()
```

**`metrics.py` — `metric_from_state()` không nhận `latency_ms`:**
```python
# Cần thêm tham số:
def metric_from_state(state, expected_route, approval_required, latency_ms=0) -> ScenarioMetric:
```

**`report.py` — render stub trống:**
- Cần viết renderer đầy đủ thay thế `render_report_stub()`

### 3.3 Chưa có (cần tạo mới)
- `app/streamlit_app.py` — Streamlit HITL UI
- `scripts/demo_crash_resume.py` — crash-resume demo
- `scripts/demo_time_travel.py` — time travel demo
- `reports/lab_report.md` — report thực (auto-generated + manual fill)

---

## 4. Kiến trúc mục tiêu

### 4.1 Graph flow (core)

```
START
  └─► intake ──► classify
                    │
          ┌─────────┼──────────────────────┐
          │         │                      │
        simple   missing_info             error
          │         │                      │
        answer    clarify               retry ◄──────────┐
          │         │                      │              │
          │         │                 tool_dispatch       │ (needs_retry)
          │         │               /           \         │
          │         │    order_lookup  customer_lookup    │
          │         │               \           /         │
          │         │                evaluate ────────────┘
          │         │                      │ (success)
          │         │                    answer
          │         │                      │
          ▼         ▼                      ▼
       finalize ──────────────────────► END
          ▲
          │
       dead_letter (khi attempt >= max_attempts)
          ▲
          │
       risky_action ──► approval ──► tool_dispatch ──► evaluate ──► ...
```

### 4.2 Retry loop logic

```
error route → retry_node (attempt += 1) → tool_dispatch
                                               │
                                           evaluate
                                           │         │
                                     success       needs_retry
                                           │         │
                                         answer     retry_node (nếu attempt < max_attempts)
                                                     │
                                                    dead_letter (nếu attempt >= max_attempts)
```

**Bound**: `attempt >= max_attempts` → `dead_letter`. set lại `max_attempts=3`.

### 4.3 Parallel fan-out (Bonus D)

```
tool_dispatch node ──► conditional edge (fan_out_to_sources)
                              │
              ┌───────────────┴───────────────┐
              │                               │
    Send("order_lookup", state)   Send("customer_lookup", state)
              │                               │
     order_lookup_node              customer_lookup_node
         (tool_results += [...])        (tool_results += [...])
              │                               │
              └───────────────┬───────────────┘
                              │  (results merged via add reducer)
                           evaluate
```

**Key**: `tool_results` dùng `Annotated[list, add]` — kết quả từ 2 node tự động merge.

---

## 5. Kế hoạch triển khai

### Phase 1 — Fix core (bắt buộc để pass tests)

**Thứ tự**: `nodes.py` → `persistence.py` → `cli.py` → `metrics.py` → `make test`

#### 5.1.1 `src/langgraph_agent_lab/nodes.py`

**`classify_node`** — dùng OpenAI LLM làm primary classifier, keyword heuristic làm fallback:

**Architecture (Hybrid)**:
```
classify_node
    │
    ├─► classify_with_llm(query)          # primary: OpenAI gpt-4o-mini
    │       │ success → (route, risk_level, reason)
    │       │ Exception (no key / timeout / rate limit)
    │       ▼
    └─► classify_with_keywords(query)     # fallback: keyword heuristic
            │
            ▼
        (route, risk_level)
```

**`classify_with_llm()`**:
- Model: `gpt-4o-mini` (default, configurable qua env `CLASSIFY_MODEL`)
- API key: `OPENAI_API_KEY` từ env
- `response_format={"type": "json_object"}` → parse JSON trả về
- `timeout=10.0` — fail fast để fallback không bị block lâu
- Trả về `tuple[Route, str, str]` — (route, risk_level, reason)

**System prompt** cho LLM:
```
Bạn là support ticket classifier. Phân loại query vào một trong các route:
- risky: refund, delete account, cancel, send email, remove, revoke
- tool: lookup, check status, track order, search, find
- missing_info: query quá ngắn/mơ hồ (< 5 từ, dùng pronoun không rõ)
- error: timeout, failure, crash, unavailable, cannot recover
- simple: default nếu không khớp

Trả về JSON: {"route": "...", "risk_level": "low|high", "reason": "..."}
```

**`classify_with_keywords()`** — keyword table với word boundary:

| Priority | Route | Keywords |
|---|---|---|
| 1 (cao nhất) | `risky` | refund, delete, send, cancel, remove, revoke |
| 2 | `tool` | status, order, lookup, check, track, find, search |
| 3 | `missing_info` | query < 5 words VÀ có pronoun ("it", "this", "that") |
| 4 | `error` | timeout, fail, error, crash, unavailable |
| 5 (default) | `simple` | Không khớp gì ở trên |

Dùng `re.search(r'\bkeyword\b', query)` — tránh "item" match "it".

**Event logging** — ghi rõ method đã dùng:
```python
make_event("classify", "completed", f"route={route} method=llm|keyword reason=...")
```

**Tất cả node functions** — thêm `latency_ms` vào `make_event()` metadata, không mutate state input.

**`tool_node`** — giữ làm fallback cho retry. Parallel fan-out dùng `order_lookup_node` + `customer_lookup_node`.

**Thêm 2 node mới cho parallel fan-out:**
```python
def tool_dispatch_node(state: AgentState) -> dict:
    """Entry point cho parallel tool lookup — state pass-through."""

def order_lookup_node(state: AgentState) -> dict:
    """Mock order DB lookup. Append kết quả vào tool_results."""

def customer_lookup_node(state: AgentState) -> dict:
    """Mock customer DB lookup. Append kết quả vào tool_results."""
```

#### 5.1.2 `src/langgraph_agent_lab/routing.py`

- `route_after_classify`: map `tool` → `"tool_dispatch"` (thay vì `"tool"`)
- Thêm `fan_out_to_sources(state)` trả về `[Send("order_lookup", state), Send("customer_lookup", state)]`
- Giữ nguyên logic các hàm còn lại

#### 5.1.3 `src/langgraph_agent_lab/graph.py`

Thêm vào graph:
```python
from langgraph.types import Send  # import cho fan-out

graph.add_node("tool_dispatch", tool_dispatch_node)
graph.add_node("order_lookup", order_lookup_node)
graph.add_node("customer_lookup", customer_lookup_node)

graph.add_conditional_edges("tool_dispatch", fan_out_to_sources, ["order_lookup", "customer_lookup"])
graph.add_edge("order_lookup", "evaluate")
graph.add_edge("customer_lookup", "evaluate")
```

Đổi `classify` → `tool` thành `classify` → `tool_dispatch` (qua `route_after_classify`).

Retry loop vẫn dùng `tool_node` gốc (single fallback), không dùng fan-out khi retry để tránh phức tạp hóa.

#### 5.1.4 `src/langgraph_agent_lab/persistence.py`

Fix SQLite API:
```python
if kind == "sqlite":
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    db_path = database_url or "outputs/checkpoints.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return SqliteSaver(conn=conn)
```

Fallback: nếu import fail → warn + trả về `MemorySaver()` thay vì crash.

#### 5.1.5 `src/langgraph_agent_lab/cli.py`

Thêm `latency_ms` measurement:
```python
import time
start = time.perf_counter()
final_state = graph.invoke(state, config=run_config)
latency_ms = int((time.perf_counter() - start) * 1000)
metrics.append(metric_from_state(final_state, scenario.expected_route.value, scenario.requires_approval, latency_ms))
```

#### 5.1.6 `src/langgraph_agent_lab/metrics.py`

Cập nhật `metric_from_state` signature:
```python
def metric_from_state(state, expected_route, approval_required, latency_ms: int = 0) -> ScenarioMetric:
    # ... existing logic ...
    return ScenarioMetric(..., latency_ms=latency_ms)
```

#### 5.1.7 `tests/test_routing.py`

Update test sau khi đổi tool route:
```python
# Đổi:
assert route_after_classify({"route": Route.TOOL.value}) == "tool"
# Thành:
assert route_after_classify({"route": Route.TOOL.value}) == "tool_dispatch"
```

---

### Phase 2 — Persistence (Bonus A: SQLite + crash-resume)

**Mục tiêu**: `resume_success: true` trong `metrics.json`, chứng minh state survives process restart.

#### `scripts/demo_crash_resume.py`

```
Bước 1: Chạy S04 (risky) với checkpointer=sqlite, thread_id="demo-crash-001"
         → Graph invoke → approval đã xảy ra → state được checkpoint
Bước 2: Simulate crash (chỉ đơn giản là not continuing)
Bước 3: Tạo graph mới với CÙNG sqlite file, CÙNG thread_id="demo-crash-001"
Bước 4: graph.get_state(config) → load state từ checkpoint cuối
Bước 5: In state trước/sau crash, verify final_answer vẫn còn
Bước 6: Ghi log evidence ra file outputs/crash_resume_evidence.txt
```

Cập nhật `configs/lab.yaml` thêm:
```yaml
checkpointer: sqlite
database_url: outputs/checkpoints.db
```

Cập nhật `cli.py` command `run-scenarios` → set `resume_success=True` nếu SQLite checkpointer.

---

### Phase 3 — Metrics & Report

#### `src/langgraph_agent_lab/report.py`

Thay `render_report_stub()` bằng renderer đầy đủ:

```markdown
# Day 08 Lab Report — LangGraph Agent

## 1. Kiến trúc hệ thống
[Mermaid diagram tự động từ graph.get_graph().draw_mermaid()]
[Giải thích các node, routing logic, retry loop]

## 2. Kết quả Metrics
| Scenario | Route | Success | Nodes | Retries | Latency |
| ...      | ...   | ...     | ...   | ...     | ...     |

- Total: X scenarios
- Success rate: Y%
- Avg nodes visited: Z
- Total retries: N

## 3. Phân tích Failure
[Tại sao scenario X failed nếu có]
[Word boundary issues nếu gặp]

## 4. Cải tiến đề xuất
[Dùng LLM thay keyword heuristics]
[Real tool integration]
[Better HITL UI]

## 5. Bonus Extensions
[Evidence cho từng extension]
```

---

### Phase 4 — Bonus B: Graph Diagram (Mermaid)

Thêm vào `cli.py` một command mới hoặc tự động export khi chạy `run-scenarios`:

```python
@app.command("export-diagram")
def export_diagram(output: Path = Path("outputs/graph_diagram.md")):
    graph = build_graph()
    mermaid_str = graph.get_graph().draw_mermaid()
    output.write_text(f"```mermaid\n{mermaid_str}\n```")
    typer.echo(f"Diagram written to {output}")
```

Nhúng diagram vào `reports/lab_report.md`.

---

### Phase 5 — Bonus C: Real HITL với Streamlit UI

#### `app/streamlit_app.py`

**Architecture**:
```
User mở app → nhập query → click "Submit"
                                │
                         graph.invoke() với LANGGRAPH_INTERRUPT=true
                                │
                         graph bị interrupt tại approval_node
                                │
                         Streamlit hiển thị:
                           - Proposed action
                           - Risk level
                           - [Approve] [Reject] buttons
                                │
                         User click → graph.invoke(Command(resume={...}))
                                │
                         Hiển thị final_answer
```

**Session state management**:
```python
# st.session_state keys:
"graph_config"    # {"configurable": {"thread_id": ...}}
"interrupted"     # bool — đang chờ approval?
"pending_state"   # state tại thời điểm interrupt
"final_answer"    # kết quả cuối
```

**Key LangGraph APIs**:
```python
from langgraph.types import Command

# Khi graph bị interrupt:
result = graph.invoke(state, config=config)
# result sẽ là interrupted state

# Resume sau khi user approve:
final = graph.invoke(Command(resume={"approved": True, "reviewer": "user"}), config=config)

# Resume sau khi reject:
final = graph.invoke(Command(resume={"approved": False, "comment": "Too risky"}), config=config)
```

**Điều kiện chạy**:
```bash
LANGGRAPH_INTERRUPT=true streamlit run app/streamlit_app.py
```

**Fallback**: Nếu `LANGGRAPH_INTERRUPT` không được set, app vẫn chạy với mock approval (hiển thị UI nhưng auto-approve).

---

### Phase 6 — Bonus E: Time Travel

#### `scripts/demo_time_travel.py`

```python
# 1. Chạy S05 (error + retry) với SQLite checkpointer
config = {"configurable": {"thread_id": "demo-timetravel-001"}}
graph.invoke(initial_state(scenario), config=config)

# 2. Lấy toàn bộ state history
history = list(graph.get_state_history(config))
# history[0] = state mới nhất, history[-1] = state đầu tiên

# 3. In tất cả checkpoints
for i, snapshot in enumerate(history):
    print(f"Checkpoint {i}: nodes={len(snapshot.values.get('events', []))}")

# 4. Replay từ checkpoint giữa chừng (ví dụ: trước lần retry đầu)
target_snapshot = history[len(history) // 2]
replay_config = {"configurable": {"thread_id": target_snapshot.config["configurable"]["thread_id"]}}
replayed = graph.invoke(None, config=target_snapshot.config)

# 5. So sánh final state giữa original run và replayed run
# 6. Ghi evidence ra outputs/time_travel_evidence.txt
```

---

## 6. Cấu trúc file sau khi hoàn thành

```
.
├── app/
│   └── streamlit_app.py          [MỚI] Streamlit HITL UI
├── configs/
│   └── lab.yaml                  [SỬA] thêm sqlite config
├── data/sample/
│   └── scenarios.jsonl           [GIỮ] 7 scenarios
├── docs/
│   ├── IMPLEMENTATION_SPEC.md    [MỚI — file này]
│   ├── LAB_GUIDE.md
│   ├── METRICS.md
│   └── RUBRIC.md
├── outputs/
│   ├── checkpoints.db            [GENERATED] SQLite checkpoints
│   ├── crash_resume_evidence.txt [GENERATED] crash-resume log
│   ├── graph_diagram.md          [GENERATED] Mermaid diagram
│   ├── metrics.json              [GENERATED] grading metrics
│   └── time_travel_evidence.txt  [GENERATED] time travel log
├── reports/
│   └── lab_report.md             [GENERATED + MANUAL]
├── scripts/
│   ├── demo_crash_resume.py      [MỚI] crash-resume demo
│   └── demo_time_travel.py       [MỚI] time travel demo
├── src/langgraph_agent_lab/
│   ├── __init__.py
│   ├── cli.py                    [SỬA] latency_ms + export-diagram command
│   ├── graph.py                  [SỬA] thêm tool_dispatch + parallel nodes
│   ├── metrics.py                [SỬA] latency_ms parameter
│   ├── nodes.py                  [SỬA] fix classify + thêm 3 nodes mới
│   ├── persistence.py            [SỬA] fix SqliteSaver API + fallback
│   ├── report.py                 [SỬA] full report renderer
│   ├── routing.py                [SỬA] tool→tool_dispatch + fan_out_to_sources
│   ├── scenarios.py
│   └── state.py
├── tests/
│   ├── test_graph_smoke.py
│   ├── test_metrics.py
│   ├── test_routing.py           [SỬA] update tool route assertion
│   └── test_state.py
└── pyproject.toml                [SỬA] thêm streamlit dependency
```

---

## 7. Các lưu ý quan trọng & Pitfalls

### 7.1 Routing priority — BẮT BUỘC phải đúng thứ tự

```python
# Priority: risky > tool > missing_info > error > simple
# Sai khi để tool check trước risky:
# "Refund this customer" → có "this" và ngắn → sẽ match missing_info trước risky
```

### 7.2 Word boundary matching

```python
import re

def has_keyword(text: str, keyword: str) -> bool:
    return bool(re.search(rf'\b{re.escape(keyword)}\b', text.lower()))

# Đúng: "Can you fix it?" → has_keyword(..., "it") = True
# Đúng: "item details" → has_keyword(..., "it") = False  (boundary!)
```

### 7.3 Unbounded retry — PHẢI có bound

```python
# route_after_retry phải check TRƯỚC khi gọi tool:
def route_after_retry(state):
    if int(state.get("attempt", 0)) >= int(state.get("max_attempts", 3)):
        return "dead_letter"
    return "tool"

# S07 có max_attempts=1:
# attempt=0 → retry_node → attempt=1 → route_after_retry → attempt(1) >= max(1) → dead_letter ✓
```

### 7.4 SqliteSaver thread safety

```python
# PHẢI dùng check_same_thread=False vì LangGraph có thể dùng multiple threads:
conn = sqlite3.connect(db_path, check_same_thread=False)
```

### 7.5 Parallel fan-out — reducer dependency

```python
# order_lookup và customer_lookup đều viết vào tool_results
# Chỉ hoạt động vì tool_results dùng Annotated[list, add]
# Nếu đổi sang field không có add reducer → race condition / overwrite
```

### 7.6 Streamlit session state

```python
# st.session_state persist giữa các reruns
# Phải clear khi user submit query mới, không để state cũ leak sang run mới
if "submit" in st.session_state:
    st.session_state.clear()
```

### 7.7 LANGGRAPH_INTERRUPT và test compatibility

```python
# Khi chạy tests và make run-scenarios, KHÔNG set LANGGRAPH_INTERRUPT=true
# approval_node check env var → nếu không set → mock approval → tests không bị block
```

### 7.8 `finalize` phải reachable từ mọi path

Kiểm tra mọi terminal node đều có edge → `finalize`:
- `answer` → `finalize` ✓
- `clarify` → `finalize` ✓
- `dead_letter` → `finalize` ✓

Thiếu edge nào → graph treo không kết thúc.

### 7.9 Không hardcode scenario ID trong routing

```python
# SAI:
if state.get("scenario_id") == "S04_risky":
    route = Route.RISKY

# ĐÚNG:
if has_keyword(query, "refund") or has_keyword(query, "delete"):
    route = Route.RISKY
```

### 7.10 LLM classify — graceful fallback

```python
# PHẢI wrap toàn bộ LLM call trong try/except rộng:
try:
    route, risk_level, reason = classify_with_llm(query)
    method = "llm"
except Exception:          # bắt cả OpenAI errors, network, JSON parse, ...
    route, risk_level = classify_with_keywords(query)
    reason = "keyword fallback"
    method = "keyword"

# KHÔNG raise lại exception — classify_node không được crash graph
```

Các lý do fallback có thể xảy ra:
- `OPENAI_API_KEY` không được set
- Rate limit / quota hết
- Network timeout (>10s)
- LLM trả về JSON không hợp lệ
- Route value không match `Route` enum

### 7.11 LLM classify — test isolation

```python
# Tests KHÔNG nên gọi OpenAI API thật (chậm, tốn tiền, không ổn định trong CI):
# Dùng monkeypatch hoặc mock classify_with_llm() trong tests:

def test_classify_node_risky(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")   # force fallback to keyword
    result = classify_node({"query": "Refund this customer"})
    assert result["route"] == "risky"
```

### 7.12 mypy và ruff compliance

```python
# Mọi function cần type annotation đầy đủ:
def classify_node(state: AgentState) -> dict:  # return dict, không dùng Any

# Imports phải có order: stdlib → third-party → local
# ruff: line length 100, target python 3.11
```

---

## 8. Testing strategy

### Unit tests (hiện có)
- `test_state.py` — validation schema, `initial_state()`
- `test_routing.py` — routing logic (**cần update** tool → tool_dispatch)
- `test_metrics.py` — metrics schema
- `test_graph_smoke.py` — smoke test 3 basic routes

### Cần thêm
- Test `classify_node` với tất cả 7 scenario queries → đúng route
- Test retry bound: `attempt >= max_attempts` → `dead_letter`
- Test parallel fan-out: cả 2 `tool_results` được merge
- Test report generation: output không phải stub

### Integration test thủ công
```bash
make test              # unit tests
make run-scenarios     # chạy 7 scenarios → outputs/metrics.json
make grade-local       # validate metrics schema
```

---

## 9. Dependencies cần thêm

```toml
# pyproject.toml — thêm vào [project.dependencies]:
"streamlit>=1.35"
"openai>=1.30"

# [project.optional-dependencies]:
sqlite = ["langgraph-checkpoint-sqlite>=2.0"]

# Install command:
pip install -e '.[dev,sqlite]'
pip install streamlit openai
```

**Environment variables** — thêm vào `.env.example`:
```bash
# OpenAI — dùng cho LLM classification (fallback to keyword nếu không set)
OPENAI_API_KEY=sk-...
CLASSIFY_MODEL=gpt-4o-mini   # optional, default: gpt-4o-mini

# LangGraph HITL — set true để bật real interrupt trong Streamlit UI
LANGGRAPH_INTERRUPT=false
```

---

## 10. Make commands cần thêm

Thêm vào `Makefile`:
```makefile
export-diagram:
    agent-lab export-diagram --output outputs/graph_diagram.md

demo-crash-resume:
    python scripts/demo_crash_resume.py

demo-time-travel:
    python scripts/demo_time_travel.py

run-streamlit:
    LANGGRAPH_INTERRUPT=true streamlit run app/streamlit_app.py
```

---

## 11. Submission checklist

### Core (bắt buộc)
- [ ] `classify_node` dùng OpenAI LLM primary + keyword fallback
- [ ] `OPENAI_API_KEY` không set → tự động fall back keyword, không crash
- [ ] Keyword fallback có đủ keywords và đúng priority
- [ ] Word boundary dùng `re.search(r'\bkeyword\b', ...)`
- [ ] `persistence.py` dùng `SqliteSaver(conn=sqlite3.connect(...))` + WAL mode
- [ ] `latency_ms` được đo và > 0 trong `metrics.json`
- [ ] `make test` pass (bao gồm test_routing.py updated)
- [ ] `make run-scenarios` → `outputs/metrics.json` valid
- [ ] `make grade-local` pass, success_rate = 1.0 (7/7 scenarios)
- [ ] `make lint` pass (ruff)
- [ ] `make typecheck` pass (mypy)
- [ ] `reports/lab_report.md` có đủ: kiến trúc, metrics table, failure analysis, improvements

### Bonus A — SQLite + crash-resume
- [ ] `configs/lab.yaml` dùng `checkpointer: sqlite`
- [ ] `scripts/demo_crash_resume.py` chạy được
- [ ] `outputs/crash_resume_evidence.txt` có log evidence
- [ ] `resume_success: true` trong `metrics.json`

### Bonus B — Mermaid diagram
- [ ] `make export-diagram` tạo `outputs/graph_diagram.md`
- [ ] Diagram nhúng vào `reports/lab_report.md`

### Bonus C — Real HITL Streamlit
- [ ] `app/streamlit_app.py` chạy được: `make run-streamlit`
- [ ] Approve/Reject buttons hoạt động
- [ ] Graph resume sau interrupt
- [ ] Screenshot/evidence trong report

### Bonus D — Parallel fan-out
- [ ] `tool_dispatch_node` → `fan_out_to_sources` → `[order_lookup, customer_lookup]`
- [ ] Cả 2 results trong `tool_results` sau khi merge
- [ ] `test_graph_smoke.py` vẫn pass với route tool

### Bonus E — Time travel
- [ ] `scripts/demo_time_travel.py` chạy được
- [ ] `outputs/time_travel_evidence.txt` in ra danh sách checkpoints
- [ ] Replay từ giữa chừng hoạt động
- [ ] Evidence trong report

---

## 12. Thứ tự triển khai khuyến nghị

```
1. Fix classify_node keywords + word boundary   → unblock routing tests
2. Fix persistence.py SqliteSaver API           → unblock SQLite
3. Fix latency_ms trong cli.py + metrics.py     → unblock metrics score
4. Update test_routing.py                       → unblock make test
5. Add tool_dispatch + parallel nodes           → Bonus D
6. make test + make run-scenarios               → verify core works
7. Fix report.py renderer                       → unlock report score
8. Export graph diagram                         → Bonus B (easy)
9. demo_crash_resume.py + update metrics        → Bonus A
10. demo_time_travel.py                         → Bonus E
11. app/streamlit_app.py                        → Bonus C (phức tạp nhất)
12. make lint + make typecheck                  → production hygiene
13. Hoàn thiện reports/lab_report.md            → report score
```
