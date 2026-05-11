# Day 08 — LangGraph Agentic Orchestration

> **Sinh viên:** Đặng Văn Minh | **MSHV:** 2A202600027
> **Môn học:** Practical AI — Phase 2 Track 3 | **Ngày nộp:** 2026-05-11

---

## Tổng quan dự án

Bài lab xây dựng một **support-ticket agent** hoàn chỉnh trên **LangGraph 1.1.6**, xử lý 7 kịch bản thực tế qua pipeline: phân loại → định tuyến → thực thi → kiểm tra → trả kết quả.

### Tính năng đã triển khai

| Tính năng | Mô tả |
|---|---|
| **Conditional routing** | 5 nhánh: `simple`, `tool`, `missing_info`, `risky`, `error` |
| **LLM classify** | OpenAI gpt-4o-mini là primary, keyword heuristic là fallback |
| **Parallel fan-out** | `Send()` chạy `order_lookup` + `customer_lookup` đồng thời |
| **Retry loop** | Bounded retry với `attempt < max_attempts`, dead-letter khi vượt giới hạn |
| **HITL approval** | `interrupt()` + `Command(resume=...)`, Streamlit UI đầy đủ |
| **SQLite persistence** | `SqliteSaver` + WAL mode, mỗi run có `thread_id` riêng |
| **Crash-resume** | Phục hồi state qua `get_state()` sau khi discard graph instance |
| **Time travel** | Replay từ checkpoint bất kỳ qua `get_state_history()` |
| **Graph diagram** | Mermaid tự động từ `draw_mermaid()` với path_map đầy đủ |

### Kết quả thực nghiệm

```
make run-scenarios
  S01_simple     : route=simple       success=True  latency=224ms
  S02_tool       : route=tool         success=True  latency=6ms
  S03_missing    : route=missing_info success=True  latency=3ms
  S04_risky      : route=risky        success=True  latency=6ms
  S05_error      : route=error        success=True  latency=7ms
  S06_delete     : route=risky        success=True  latency=7ms
  S07_dead_letter: route=error        success=True  latency=4ms

success_rate=100%  scenarios=7/7
```

---

## Cài đặt & Chạy nhanh

```bash
# 1. Cài đặt
pip install -e '.[dev,sqlite]'

# 2. (Tùy chọn) Cấu hình OpenAI API key cho LLM classify
cp .env.example .env
# Điền OPENAI_API_KEY=sk-... vào .env
# Nếu bỏ qua → keyword fallback tự động kích hoạt

# 3. Chạy toàn bộ thực nghiệm
make run-scenarios    # 7 scenarios → outputs/metrics.json
make test             # 11 unit tests
make lint             # ruff
make typecheck        # mypy
make grade-local      # validate metrics
```

Xem hướng dẫn chi tiết từng thực nghiệm: [`docs/run_docs.md`](docs/run_docs.md)

---

## Hướng dẫn chấm bài

### Bước 1 — Cài đặt môi trường

```bash
pip install -e '.[dev,sqlite]'
python3 -c "import langgraph_agent_lab; print('OK')"
```

---

### Bước 2 — Chạy toàn bộ pipeline kiểm tra

```bash
make run-scenarios && \
make lint && \
make typecheck && \
make test && \
make grade-local
```

**Kết quả kỳ vọng:**

```
success_rate=100.00%  scenarios=7
All checks passed!
Success: no issues found in 10 source files
11 passed in 0.40s
Metrics valid. success_rate=100.00%
```

---

### Bước 3 — Đối chiếu từng tiêu chí rubric

#### Tiêu chí 1: Kiến trúc & State Schema 

| Kiểm tra | Lệnh / File |
|---|---|
| Typed state với reducers đúng | `src/langgraph_agent_lab/state.py` — xem `AgentState` |
| `Annotated[list, add]` cho append-only fields | `state.py` line 60–63: `tool_results`, `events`, `errors`, `messages` |
| Node boundaries rõ ràng | `src/langgraph_agent_lab/nodes.py` — mỗi node trả `dict` partial |
| 14 node được khai báo | `src/langgraph_agent_lab/graph.py` |

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from langgraph_agent_lab.graph import build_graph
g = build_graph()
print('Nodes:', list(g.get_graph().nodes.keys()))
"
```

---

#### Tiêu chí 2: Graph Behavior 

**Kiểm tra routing đúng 7 scenarios:**

```bash
make run-scenarios
# Xem outputs/metrics.json — tất cả actual_route == expected_route
```

**Kiểm tra bounded retry (S05, S07):**

```bash
python3 -c "
import json
m = json.load(open('outputs/metrics.json'))
for s in m['scenario_metrics']:
    if s['retry_count'] > 0:
        print(s['scenario_id'], 'retries:', s['retry_count'], 'success:', s['success'])
"
# S05: 8 retries, success=True (loop kết thúc đúng)
# S07: 4 retries, success=True (dead-letter khi max_attempts=1)
```

**Kiểm tra HITL path (S04, S06):**

```bash
python3 -c "
import json
m = json.load(open('outputs/metrics.json'))
for s in m['scenario_metrics']:
    if s['approval_observed']:
        print(s['scenario_id'], 'approval_observed:', s['approval_observed'])
"
# S04, S06: approval_observed=True
```

---

#### Tiêu chí 3: Persistence & Recovery 

**Crash-resume demo:**

```bash
make demo-crash-resume
# Xem outputs/crash_resume_evidence.txt
# Phải có: "[OK] State successfully recovered from SQLite checkpoint!"
```

**Thread ID per run — kiểm tra:**

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
g = build_graph(checkpointer=build_checkpointer('sqlite', 'outputs/verify.db'))
from langgraph_agent_lab.state import Scenario, Route, initial_state
s = initial_state(Scenario(id='verify-01', query='How to reset password', expected_route=Route.SIMPLE))
s['thread_id'] = 'verify-01'
r = g.invoke(s, config={'configurable': {'thread_id': 'verify-01'}})
snap = g.get_state({'configurable': {'thread_id': 'verify-01'}})
history = list(g.get_state_history({'configurable': {'thread_id': 'verify-01'}}))
print('thread_id:', r.get('thread_id'))
print('checkpoints:', len(history))
"
```

---

#### Tiêu chí 4: Metrics & Tests 

```bash
# Unit tests
make test
# Kỳ vọng: 11 passed

# Metrics schema validation
make grade-local
# Kỳ vọng: Metrics valid. success_rate=100.00%

# Xem chi tiết metrics
python3 -c "
import json
m = json.load(open('outputs/metrics.json'))
print('scenarios :', m['total_scenarios'])
print('success   :', f\"{m['success_rate']:.0%}\")
print('avg_nodes :', f\"{m['avg_nodes_visited']:.1f}\")
print('retries   :', m['total_retries'])
print('interrupts:', m['total_interrupts'])
"
```

---

#### Tiêu chí 5: Report & Demo 

```bash
# Sinh report từ data thực
make run-scenarios   # cần chạy trước để có metrics.json
cat reports/lab_report.md
```

Report tại `reports/lab_report.md` bao gồm:
- Diagram Mermaid (Section 1.2)
- State schema annotated (Section 1.4)
- Bảng metrics 7 scenarios (Section 4.1)
- Phân tích retry & latency (Section 4.2, 4.3)
- Failure analysis (Section 5.1)
- 6 điểm cải tiến đề xuất (Section 5.2)

---

#### Tiêu chí 6: Production Hygiene 

```bash
make lint       # ruff — All checks passed
make typecheck  # mypy — no issues found
```

Kiểm tra thêm:
- `.env.example` — không commit secrets thật
- `configs/lab.yaml` — config tách khỏi code
- `.gitignore` — loại bỏ `outputs/`, `*.db`, `.env`

---

### Bước 4 — Kiểm tra 5 Bonus Extensions

#### Bonus A — SQLite Crash-Resume

```bash
make demo-crash-resume
# Kết quả cuối: "RESULT: PASS — SQLite persistence survives simulated restart"
cat outputs/crash_resume_evidence.txt
```

#### Bonus B — Graph Diagram

```bash
make export-diagram
cat outputs/graph_diagram.md
# Phải có đủ edges: classify → 5 nhánh, retry loop, approval conditional
```

#### Bonus C — Streamlit HITL UI

```bash
make run-streamlit
# Mở http://localhost:8501
# Test: nhập "Refund this customer" → Submit
# Kỳ vọng: màn hình Approval xuất hiện với risk=HIGH
# Click Approve → Complete screen với approval=True
```

#### Bonus D — Parallel Fan-out

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.state import Scenario, Route, initial_state
g = build_graph()
s = initial_state(Scenario(id='t', query='lookup order status for order 99', expected_route=Route.TOOL))
r = g.invoke(s, config={'configurable': {'thread_id': 't'}})
print('tool_results count:', len(r['tool_results']))
print('sources:', r['tool_results'])
# Kỳ vọng: 2 entries — ORDER_DB + CUSTOMER_DB
"
```

#### Bonus E — Time Travel

```bash
make demo-time-travel
# Kết quả cuối: "RESULT: PASS — get_state_history() + replay from past checkpoint works"
# routes match: True
cat outputs/time_travel_evidence.txt
```

---

### Tóm tắt điểm chấm

| Tiêu chí | Điểm tối đa | Lệnh kiểm tra |
|---|:---:|---|
| Kiến trúc & State Schema | 20 | Đọc `state.py`, `nodes.py`, `graph.py` |
| Graph Behavior | 25 | `make run-scenarios` + kiểm tra routing/retry/HITL |
| Persistence & Recovery | 15 | `make demo-crash-resume` |
| Metrics & Tests | 20 | `make test` + `make grade-local` |
| Report & Demo | 15 | `cat reports/lab_report.md` |
| Production Hygiene | 5 | `make lint` + `make typecheck` |
| **Tổng core** | **100** | |
| Bonus A — Crash-Resume | +5 | `outputs/crash_resume_evidence.txt` |
| Bonus B — Diagram | +5 | `outputs/graph_diagram.md` |
| Bonus C — Streamlit HITL | +5 | `make run-streamlit` |
| Bonus D — Parallel Fan-out | +5 | 2 entries trong `tool_results` |
| Bonus E — Time Travel | +5 | `outputs/time_travel_evidence.txt` |

---

## Cấu trúc dự án

```
├── app/
│   └── streamlit_app.py          # Bonus C: HITL UI
├── configs/
│   └── lab.yaml                  # checkpointer: sqlite
├── data/sample/
│   └── scenarios.jsonl           # 7 test scenarios
├── docs/
│   ├── IMPLEMENTATION_SPEC.md    # thiết kế chi tiết
│   └── run_docs.md               # hướng dẫn chạy thực nghiệm
├── outputs/                      # generated — gitignored
│   ├── metrics.json
│   ├── graph_diagram.md
│   ├── crash_resume_evidence.txt
│   └── time_travel_evidence.txt
├── reports/
│   └── lab_report.md             # báo cáo tự sinh từ data
├── scripts/
│   ├── demo_crash_resume.py      # Bonus A
│   └── demo_time_travel.py       # Bonus E
├── src/langgraph_agent_lab/
│   ├── state.py       # AgentState + reducers
│   ├── nodes.py       # 14 node implementations
│   ├── routing.py     # conditional edge functions
│   ├── graph.py       # StateGraph wiring
│   ├── persistence.py # SqliteSaver + MemorySaver
│   ├── metrics.py     # MetricsReport schema
│   ├── cli.py         # typer CLI
│   └── report.py      # report generator
├── tests/             # 11 unit tests
├── .env.example
├── Makefile
└── pyproject.toml
```

## Make commands

| Lệnh | Mô tả |
|---|---|
| `make install` | Cài đặt dependencies |
| `make test` | Chạy pytest (11 tests) |
| `make lint` | ruff check |
| `make typecheck` | mypy check |
| `make run-scenarios` | Chạy 7 scenarios → `outputs/metrics.json` |
| `make grade-local` | Validate metrics |
| `make export-diagram` | Xuất Mermaid diagram |
| `make demo-crash-resume` | Demo Bonus A |
| `make demo-time-travel` | Demo Bonus E |
| `make run-streamlit` | Khởi động HITL UI (Bonus C) |
| `make clean` | Xóa cache và generated files |
