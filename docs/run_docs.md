# Hướng dẫn chạy thực nghiệm — Day 08 LangGraph Agent Lab

> Tài liệu này mô tả đầy đủ từng bước cài đặt, cấu hình và chạy tất cả thực nghiệm trong lab.

---

## Mục lục

1. [Yêu cầu môi trường](#1-yêu-cầu-môi-trường)
2. [Cài đặt](#2-cài-đặt)
3. [Cấu hình biến môi trường](#3-cấu-hình-biến-môi-trường)
4. [Chạy toàn bộ scenarios (core lab)](#4-chạy-toàn-bộ-scenarios-core-lab)
5. [Kiểm tra chất lượng code](#5-kiểm-tra-chất-lượng-code)
6. [Bonus A — SQLite Crash-Resume](#6-bonus-a--sqlite-crash-resume)
7. [Bonus B — Xuất Graph Diagram](#7-bonus-b--xuất-graph-diagram)
8. [Bonus C — Streamlit HITL UI](#8-bonus-c--streamlit-hitl-ui)
9. [Bonus D — Parallel Fan-out](#9-bonus-d--parallel-fan-out)
10. [Bonus E — Time Travel](#10-bonus-e--time-travel)
11. [Xem kết quả đầu ra](#11-xem-kết-quả-đầu-ra)
12. [Chạy nhanh toàn bộ (one-liner)](#12-chạy-nhanh-toàn-bộ-one-liner)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Yêu cầu môi trường

| Thành phần | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| Python | 3.11+ | Đã test trên 3.12.6 |
| pip | 23+ | Đi kèm Python |
| OpenAI API key | — | Tùy chọn — nếu không có thì dùng keyword fallback |
| SQLite | Có sẵn trong stdlib | Không cần cài thêm |
| Internet | — | Chỉ cần khi gọi OpenAI API |

Kiểm tra phiên bản Python đang dùng:

```bash
python3 --version
```

---

## 2. Cài đặt

```bash
# Clone repo (nếu chưa có)
git clone <repo-url>
cd phase2-track3-day8-langgraph-agent

# Cài đặt package và tất cả dependencies (bao gồm SQLite checkpointer và dev tools)
pip install -e '.[dev,sqlite]'

# Xác nhận cài đặt thành công
python3 -c "import langgraph; import streamlit; import openai; print('OK')"
```

Các package chính được cài:

| Package | Phiên bản | Vai trò |
|---|---|---|
| `langgraph` | 1.1.6+ | Core graph orchestration |
| `langgraph-checkpoint-sqlite` | 2.0+ | SQLite persistence |
| `openai` | 1.30+ | LLM classification |
| `streamlit` | 1.35+ | HITL UI |
| `typer` | 0.12+ | CLI commands |
| `pydantic` | 2.7+ | State schema validation |

---

## 3. Cấu hình biến môi trường

Tạo file `.env` từ template:

```bash
cp .env.example .env
```

Mở `.env` và điền các giá trị:

```dotenv
# OpenAI — dùng cho LLM classification (gpt-4o-mini)
# Nếu không set → tự động fallback sang keyword heuristic (không crash)
OPENAI_API_KEY=sk-your-key-here
CLASSIFY_MODEL=gpt-4o-mini

# LangGraph HITL — chỉ cần khi chạy Streamlit UI
# "true" → bật real interrupt(), "false" → mock approval
LANGGRAPH_INTERRUPT=false

# Persistence backend
CHECKPOINTER=memory
DATABASE_URL=outputs/checkpoints.db

LOG_LEVEL=INFO
```

**Lưu ý:**
- `OPENAI_API_KEY` là **tùy chọn** — không cần thiết để chạy scenarios cơ bản
- Khi không có key, `classify_node` tự động dùng keyword heuristic (route vẫn đúng cho 6/7 scenarios)
- `LANGGRAPH_INTERRUPT=true` **chỉ dùng khi chạy Streamlit UI** — để trong file `.env` là `false`

Load biến môi trường trước khi chạy:

```bash
export $(grep -v '^#' .env | xargs)
# hoặc dùng direnv nếu đã cài
```

---

## 4. Chạy toàn bộ scenarios (core lab)

Đây là lệnh chính để chạy 7 scenario và tạo metrics report.

```bash
make run-scenarios
```

Tương đương:

```bash
python3 -m langgraph_agent_lab.cli run-scenarios \
    --config configs/lab.yaml \
    --output outputs/metrics.json
```

**Output mẫu:**

```
  S01_simple     : route=simple       success=True  latency=208ms
  S02_tool       : route=tool         success=True  latency=5ms
  S03_missing    : route=missing_info success=True  latency=3ms
  S04_risky      : route=risky        success=True  latency=5ms
  S05_error      : route=error        success=True  latency=6ms
  S06_delete     : route=risky        success=True  latency=5ms
  S07_dead_letter: route=error        success=True  latency=3ms

Wrote metrics to outputs/metrics.json
success_rate=100.00%  scenarios=7
```

**Kiểm tra kết quả (grading):**

```bash
make grade-local
```

Tương đương:

```bash
python3 -m langgraph_agent_lab.cli validate-metrics \
    --metrics outputs/metrics.json
```

**7 Scenarios được test:**

| ID | Query | Route | Đặc điểm |
|---|---|---|---|
| S01_simple | How do I reset my password? | `simple` | Direct answer, no tool |
| S02_tool | Please lookup order status for order 12345 | `tool` | Parallel fan-out (order + customer DB) |
| S03_missing | Can you fix it? | `missing_info` | Thiếu thông tin → clarify |
| S04_risky | Refund this customer and send confirmation email | `risky` | HITL approval (mock) |
| S05_error | Timeout failure while processing request | `error` | Retry loop (3 lần) |
| S06_delete | Delete customer account after support verification | `risky` | HITL approval (mock) |
| S07_dead_letter | System failure cannot recover after multiple attempts | `error` | Dead-letter (max_attempts=1) |

---

## 5. Kiểm tra chất lượng code

Chạy cả ba bước kiểm tra cùng lúc:

```bash
make lint && make typecheck && make test
```

Hoặc từng bước:

```bash
# Lint (ruff — E, F, I, B, UP, N, ANN rules)
make lint

# Type check (mypy strict)
make typecheck

# Unit tests (pytest)
make test
```

**Output kỳ vọng:**

```
ruff check src tests
All checks passed!

mypy src --ignore-missing-imports
Success: no issues found in 10 source files

pytest
...........
11 passed in 0.40s
```

---

## 6. Bonus A — SQLite Crash-Resume

Demo chứng minh SQLite persistence sống sót qua "process crash":

```bash
make demo-crash-resume
```

Tương đương:

```bash
python3 scripts/demo_crash_resume.py
```

**Các bước demo thực hiện:**

1. Chạy S04_risky với SQLite checkpointer → lưu vào `outputs/demo_crash_checkpoints.db`
2. Xóa graph instance (`del graph1`) — mô phỏng crash
3. Tạo graph mới với **cùng file SQLite**
4. Gọi `graph.get_state(config)` → khôi phục state từ checkpoint
5. Liệt kê toàn bộ checkpoint history
6. Ghi evidence ra `outputs/crash_resume_evidence.txt`

**Output mẫu (phần cuối):**

```
STEP 4: State history — intermediate checkpoints
----------------------------------------
  Total checkpoints saved: 21

  [00] last_node=finalize         attempt=0  nodes_so_far=11
  [01] last_node=answer           attempt=0  nodes_so_far=10
  ...
  [20] last_node=—                attempt=0  nodes_so_far=0

============================================================
RESULT: PASS — SQLite persistence survives simulated restart
============================================================

Evidence written → outputs/crash_resume_evidence.txt
```

---

## 7. Bonus B — Xuất Graph Diagram

Xuất sơ đồ Mermaid của toàn bộ graph:

```bash
make export-diagram
```

Tương đương:

```bash
python3 -m langgraph_agent_lab.cli export-diagram \
    --output outputs/graph_diagram.md
```

File `outputs/graph_diagram.md` chứa block Mermaid có thể render trên GitHub / VS Code:

```markdown
```mermaid
graph TD
    intake --> classify
    classify -->|simple| answer
    classify -->|tool| tool_dispatch
    classify -->|risky| risky_action
    ...
```​
```

---

## 8. Bonus C — Streamlit HITL UI

### Khởi động UI

```bash
make run-streamlit
```

Tương đương:

```bash
LANGGRAPH_INTERRUPT=true streamlit run app/streamlit_app.py
```

Truy cập: **http://localhost:8501**

### Luồng HITL đầy đủ

**Bước 1 — Nhập query risky:**

Trong sidebar click ví dụ `🔴 Risky — refund` hoặc tự nhập:

```
Refund this customer and send confirmation email
```

Nhấn **Submit ticket**.

**Bước 2 — Màn hình approval xuất hiện:**

- Hiển thị `Risk level: 🔴 HIGH` và `Route: RISKY`
- Box `Proposed action` mô tả hành động cần duyệt
- Accordion `📜 Audit events so far` — xem lịch sử node đã chạy

**Bước 3 — Quyết định:**

- Điền `Reviewer name` (mặc định: `human-reviewer`)
- Điền `Comment` (tùy chọn)
- Nhấn **✅ Approve** hoặc **❌ Reject**

**Bước 4 — Xem kết quả:**

- Summary metrics: Route, Nodes, Retries, Approval
- Final answer (xanh = approved, vàng = rejected)
- `🔧 Tool results` — kết quả từ order DB + customer DB
- `📜 Full audit log` — toàn bộ node path

**Các ví dụ trong sidebar:**

| Icon | Label | Mô tả |
|---|---|---|
| 🟢 | Simple | Không cần tool, không cần approval |
| 🔵 | Tool lookup | Trigger parallel fan-out |
| 🟡 | Missing info | Hỏi lại clarification |
| 🔴 | Risky — refund | Kích hoạt HITL interrupt |
| 🔴 | Risky — delete | Kích hoạt HITL interrupt |
| ⚫ | Error / retry | Retry loop → dead-letter |

### Mock mode (không cần HITL)

Chạy không có env var để dùng mock approval (phù hợp khi demo offline):

```bash
streamlit run app/streamlit_app.py
```

Sidebar sẽ hiển thị `⚠️ HITL mock mode`.

---

## 9. Bonus D — Parallel Fan-out

Không cần chạy script riêng — parallel fan-out được kích hoạt **tự động** khi route là `tool`.

Chạy S02_tool để quan sát:

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.state import Route, Scenario, initial_state

graph = build_graph()
scenario = Scenario(id='test', query='Please lookup order status for order 12345', expected_route=Route.TOOL)
state = initial_state(scenario)
result = graph.invoke(state, config={'configurable': {'thread_id': 'test-fanout'}})

print('route       :', result['route'])
print('tool_results:', result['tool_results'])
print('nodes visited:', [e['node'] for e in result['events']])
"
```

**Output mẫu:**

```
route       : tool
tool_results: [
  'ORDER_DB: order found | scenario=test | status=delivered',
  'CUSTOMER_DB: customer active | scenario=test | tier=premium'
]
nodes visited: ['intake', 'classify', 'tool_dispatch', 'order_lookup', 'customer_lookup', 'evaluate', 'answer', 'finalize']
```

`order_lookup` và `customer_lookup` chạy **song song** qua `Send()`, kết quả merge vào `tool_results` via `Annotated[list, add]` reducer.

---

## 10. Bonus E — Time Travel

Demo replay graph từ checkpoint trung gian:

```bash
make demo-time-travel
```

Tương đương:

```bash
python3 scripts/demo_time_travel.py
```

**Các bước demo thực hiện:**

1. Chạy S05_error → tạo nhiều checkpoint (retry loop sinh ~12 checkpoint)
2. Gọi `graph.get_state_history(config)` → liệt kê tất cả
3. Chọn checkpoint tại `attempt=1` (giữa chừng, chưa hoàn thành)
4. Replay: `graph.invoke(None, config=snapshot.config)` → graph tiếp tục từ đó
5. So sánh route original vs replayed

**Output mẫu:**

```
STEP 2: State history — all checkpoints
  Total checkpoints: 12

  [00] last=finalize          attempt=2  eval=success
  [01] last=answer            attempt=2  eval=success
  ...
  [06] last=retry             attempt=1  eval=needs_retry
  ...

STEP 3: Selected checkpoint: attempt=1, nodes_so_far=[..., 'retry']

STEP 4: Replay from selected checkpoint
  route         : error
  nodes visited : ['retry', 'tool', 'evaluate', 'answer', 'finalize']
  final_answer  : Here is what I found: ...

STEP 5: Compare original vs replayed
  original route  : error
  replayed route  : error
  routes match    : True

============================================================
RESULT: PASS — get_state_history() + replay from past checkpoint works
============================================================
```

---

## 11. Xem kết quả đầu ra

Sau khi chạy, các file kết quả nằm trong `outputs/`:

```
outputs/
├── metrics.json              ← Kết quả 7 scenarios (JSON)
├── graph_diagram.md          ← Mermaid diagram
├── crash_resume_evidence.txt ← Evidence Bonus A
├── time_travel_evidence.txt  ← Evidence Bonus E
├── checkpoints.db            ← SQLite từ run-scenarios
├── demo_crash_checkpoints.db ← SQLite từ demo crash-resume
├── demo_timetravel_checkpoints.db
└── streamlit_checkpoints.db  ← SQLite từ Streamlit UI
```

Xem metrics JSON:

```bash
cat outputs/metrics.json | python3 -m json.tool
```

Xem crash-resume evidence:

```bash
cat outputs/crash_resume_evidence.txt
```

Xem time travel evidence:

```bash
cat outputs/time_travel_evidence.txt
```

Lab report đầy đủ (sau khi `run-scenarios`):

```bash
cat reports/lab_report.md
```

---

## 12. Chạy nhanh toàn bộ (one-liner)

Chạy toàn bộ thực nghiệm theo thứ tự:

```bash
# 1. Core scenarios
make run-scenarios

# 2. Code quality
make lint && make typecheck && make test

# 3. Grading
make grade-local

# 4. Bonus A: Crash-resume
make demo-crash-resume

# 5. Bonus B: Diagram
make export-diagram

# 6. Bonus E: Time travel
make demo-time-travel

# 7. Bonus C: HITL UI (mở browser riêng)
make run-streamlit
```

Hoặc gộp tất cả trừ Streamlit (non-interactive):

```bash
make run-scenarios && \
make lint && make typecheck && make test && \
make grade-local && \
make demo-crash-resume && \
make export-diagram && \
make demo-time-travel && \
echo "=== All experiments completed ==="
```

---

## 13. Troubleshooting

### `OPENAI_API_KEY` không hợp lệ

```
Error: OPENAI_API_KEY not set
```

**Giải pháp:** Bỏ qua nếu không cần LLM classify — keyword fallback tự động kích hoạt. Nếu muốn dùng LLM: `export OPENAI_API_KEY=sk-...`

---

### Package chưa được cài

```
ModuleNotFoundError: No module named 'langgraph_agent_lab'
```

**Giải pháp:**

```bash
pip install -e '.[dev,sqlite]'
```

---

### Dùng sai Python (nhiều môi trường)

```
ModuleNotFoundError khi dùng `python` thay vì `python3`
```

**Giải pháp:** Luôn dùng `python3` (đã được set trong Makefile). Xác nhận:

```bash
which python3 && python3 -c "import langgraph_agent_lab"
```

---

### SQLite file bị lock

```
sqlite3.OperationalError: database is locked
```

**Giải pháp:** Đóng Streamlit app đang chạy hoặc xóa file `.db`:

```bash
rm -f outputs/*.db
```

---

### Streamlit không nhận HITL interrupt

Khi click Submit nhưng không hiện màn hình approval:

1. Xác nhận server khởi động với `LANGGRAPH_INTERRUPT=true`:
   ```bash
   make run-streamlit
   # Không dùng: streamlit run app/streamlit_app.py (thiếu env var)
   ```
2. Dùng query risky rõ ràng: `Refund this customer` hoặc `Delete customer account`
3. Sidebar phải hiển thị `HITL enabled — real interrupt() active` (màu xanh)

---

### `make grade-local` báo fail

Xác nhận `outputs/metrics.json` tồn tại và có đủ 7 scenarios:

```bash
python3 -c "
import json
m = json.load(open('outputs/metrics.json'))
print('scenarios:', len(m.get('scenario_metrics', [])))
print('success_rate:', m.get('success_rate'))
"
```

Nếu thiếu, chạy lại `make run-scenarios` trước.
