# Temporal Payment Processing POC

A small **fake** payment system that shows how [Temporal](https://temporal.io) fits into a real
application: React → FastAPI → Temporal → Worker → Workflow → Activities.

> Learning project only. No real bank, gateway or money is involved. Accounts and balances live
> in a local SQLite file.

---

## Run it on a new machine (after `git clone`)

The only thing you need is **[Docker Desktop](https://www.docker.com/products/docker-desktop/)**
(Windows / macOS) or Docker Engine + Compose plugin (Linux). No Python or Node install needed.

**1. Clone the repo**

```bash
git clone https://github.com/vivek-kapilit/demo_Temporal_workflow.git
cd demo_Temporal_workflow
```

**2. Make sure Docker is running** (open Docker Desktop and wait until it says *Engine running*).

**3. Build and start everything** (run from the folder that contains `docker-compose.yml`):

```bash
docker compose up -d --build
```

The first run takes a few minutes while images are downloaded and built.

**4. Check that all 4 containers are up**

```bash
docker compose ps
```

You should see `temporal-dev`, `payment-api`, `payment-worker` and `payment-frontend` all with
status **Up**.

**5. Open the app**

| What | URL |
|---|---|
| **Payment app (frontend)** | **<http://localhost:3000>** |
| Temporal Web UI (workflow history) | <http://localhost:8233> |
| API docs (Swagger) | <http://localhost:8000/docs> |

> **Note:** port 8233 is the *Temporal* UI, not the app. The payment app is on **port 3000**.

**Stop / reset**

```bash
docker compose down        # stop everything, keep data
docker compose down -v     # stop and wipe all data (balances reset, workflow history deleted)
```

### Troubleshooting

| Problem | Fix |
|---|---|
| Only `temporal-dev` is running / no frontend link, only the Temporal UI opens | You started Temporal alone (`docker compose up -d temporal`). Run `docker compose up -d --build` to start all 4 containers. |
| `Cannot connect to the Docker daemon` / `pipe/docker_engine` error | Docker Desktop is not running. Start it and retry. |
| `port is already allocated` (3000, 8000, 7233 or 8233) | Another program uses that port. Stop it, or change the left-hand port in `docker-compose.yml` (e.g. `"3001:80"`). |
| `payment-worker` shows **Exited** | Start it again: `docker start payment-worker`. See logs with `docker compose logs worker`. |
| App loads but shows errors / no accounts | Check the API: `docker compose logs api`. Then restart: `docker compose restart api`. |
| Changed code but nothing changed in the app | Rebuild: `docker compose up -d --build`. |

---

## 1. What Temporal is doing in this project

Creating a payment runs a multi-step business process. Any step can fail, be slow, or wait for a
human. The worker process can also crash halfway through.

Temporal **owns that process**:

| Concern | Who handles it |
|---|---|
| Order of steps, business decisions (approval needed?) | **Workflow** (`PaymentWorkflow`) |
| Actual work: DB reads/writes, "bank" call, notification | **Activities** |
| Retrying failed steps, enforcing timeouts | **Temporal Server** (using the policies the workflow declares) |
| Remembering where each payment is, even if everything restarts | **Temporal Server** (workflow *history*) |
| Waiting days for an approval without holding a thread | **Temporal timer + signal** |
| Running the code | **Worker** process you start yourself |

FastAPI never runs payment logic. It only talks to Temporal through the **Temporal Client**.

## 2. Architecture

```text
 ┌──────────────┐  HTTP /api/*   ┌──────────────────────┐
 │ React (Vite) │ ─────────────▶ │ FastAPI  (app/main)  │
 │  :5173       │ ◀───────────── │  :8000               │
 └──────────────┘   poll 1s      │  Temporal CLIENT     │
                                 └──────────┬───────────┘
                start_workflow / signal /   │ gRPC :7233
                query / describe / history  ▼
                                 ┌──────────────────────┐   Web UI :8233
                                 │   TEMPORAL SERVER    │ ◀──── you (browser)
                                 │ (docker, dev server) │
                                 │ task queue:          │
                                 │  payment-task-queue  │
                                 └──────────┬───────────┘
                     long-poll for tasks,   │ gRPC :7233
                     report results         ▼
                                 ┌──────────────────────┐        ┌──────────────┐
                                 │ WORKER process       │        │ SQLite       │
                                 │ (app/temporal_worker)│        │ payments.db  │
                                 │  ├ PaymentWorkflow   │        │ accounts     │
                                 │  └ Activities ───────┼──────▶ │ ledger       │
                                 └──────────────────────┘        │ transactions │
                                                                 │ notifications│
                                                                 └──────────────┘
```

Workflow steps:

```text
Payment Created → Validate → Check Balance → Fraud Check → [Approval if > ₹50,000]
               → Process Payment → Save Transaction → Send Notification → Completed
```

### Project layout

```text
docker-compose.yml               full stack: temporal, api, worker, frontend
backend/
  Dockerfile                     one image, used for both api and worker
  requirements.txt
  .env.example                   all configuration (copied to .env)
  app/
    main.py                      FastAPI app, connects Temporal client on startup
    config.py                    reads environment variables
    db.py                        SQLite schema + seed accounts
    temporal_client.py           Temporal CLIENT (used by FastAPI)
    temporal_worker.py           Temporal WORKER (separate process)
    api/payments.py              REST endpoints → Temporal client calls
    workflows/payment_workflow.py  PaymentWorkflow: orchestration only, deterministic
    activities/payment_activities.py  the steps: all I/O and side effects
    models/payment.py            dataclasses passed through Temporal
    models/api.py                request bodies
frontend/
  Dockerfile, nginx.conf         production build served by nginx, /api proxied to FastAPI
  src/
    pages/Dashboard.jsx          form + live panel + payment list + accounts
    pages/PaymentPage.jsx        full details page (/payments/:workflowId)
    components/                  form, step timeline, history table, details
    services/api.js              calls to FastAPI
```

## 3. How the FastAPI → Temporal → Worker flow works

1. **React** `POST /api/payments` with sender, receiver, amount and the failure switches.
2. **FastAPI** (`api/payments.py`) calls `client.start_workflow(PaymentWorkflow.run, ...)` with a
   unique workflow ID (`payment-PAY-XXXX`) on task queue `payment-task-queue`, then **returns
   immediately**. Nothing has run yet.
3. **Temporal Server** records `WorkflowExecutionStarted` in the history and puts a *workflow
   task* on the queue.
4. **Worker** picks up the task and runs `PaymentWorkflow.run` until it reaches
   `execute_activity(validate_payment)`. That produces a command, "schedule activity", which goes
   back to the server.
5. The server puts an *activity task* on the queue. The worker runs `validate_payment` and
   reports the result, which the server writes to the history. The workflow then continues to the
   next step, and so on.
6. **React polls** `GET /api/payments/{id}` every second. FastAPI builds the answer from:
   * `describe()`: Temporal status (RUNNING/COMPLETED/FAILED) and **pending activities**
     (current attempt number, last failure, including retries happening right now)
   * `query(get_status)`: the workflow's own state (steps, approval, transaction ID)
   * the **history**: how many attempts each activity took
7. For approvals, React calls `POST /api/payments/{id}/approve|reject`. FastAPI sends a **signal**
   to the workflow, and the waiting workflow wakes up.

### Workflow vs Activity: why the split?

* The **workflow** is replayed from history after a crash, so it must be *deterministic*. It
  must not do DB access, network calls, `random`, `uuid4()`, `datetime.now()` or `sleep()`. It
  only decides what happens next.
* **Activities** do the real work and may do anything. Temporal retries them and times them out.
  Because they can run more than once, the ones that change data are **idempotent**
  (`process_payment` checks the `ledger` table by `payment_id` so money never moves twice).

## Quick start: everything in Docker

Requires only Docker. One command builds and starts all four processes:

```bash
docker compose up -d --build
```

| Container | What it runs | URL |
|---|---|---|
| `temporal-dev` | Temporal Server + Web UI | UI <http://localhost:8233>, gRPC `localhost:7233` |
| `payment-api` | FastAPI + Temporal Client (`backend/Dockerfile`) | <http://localhost:8000/docs> |
| `payment-worker` | Temporal Worker (same image, `python -m app.temporal_worker`) | - |
| `payment-frontend` | React build served by nginx; nginx proxies `/api` to `payment-api` | **<http://localhost:3000>** |

The API and worker share the SQLite file through the `app-data` volume. Temporal's history is on
the `temporal-data` volume. Configuration is set in `docker-compose.yml` under `x-backend-env`.

Useful commands:

```bash
docker compose ps                     # status of all containers
docker compose logs -f worker         # watch the worker run activities (and retries)
docker compose logs -f api
docker kill payment-worker            # simulate a worker crash (section 10)
docker start payment-worker           # bring it back; workflows continue
docker compose down                   # stop everything (data kept)
docker compose down -v                # stop and wipe all data (balances + workflow history)
```

After changing Python or React code, run `docker compose up -d --build` again.

With Docker, use **<http://localhost:3000>** wherever this README says `localhost:5173`. Sections
4–6 below are for running the backend and frontend **outside** Docker, which is handy while
editing code.

## 4. Start Temporal locally

Requires Docker. To start **only** Temporal (then run backend and frontend locally):

```bash
docker compose up -d temporal
```

* gRPC endpoint: `localhost:7233`
* Temporal Web UI: <http://localhost:8233>

This runs the official `temporalio/temporal` image in `server start-dev` mode, with its SQLite
database on a Docker volume. Workflows therefore survive `docker compose restart`. To wipe all
workflow history: `docker compose down -v`.

## 5. Start the backend

Requires Python 3.10+. You need **two terminals**, one for the API and one for the worker.

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
```

Terminal 1: the **worker** (runs workflows + activities):

```bash
cd backend && .venv\Scripts\activate     # (or source .venv/bin/activate)
python -m app.temporal_worker
```

Terminal 2: the **API** (Temporal client):

```bash
cd backend && .venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>. The SQLite file `backend/payments.db` is created and
seeded automatically:

| Account | Owner | Starting balance |
|---|---|---|
| ACC-1001 | Alice | ₹1,00,000 |
| ACC-1002 | Bob | ₹2,50,000 |
| ACC-1003 | Charlie | ₹5,000 |
| ACC-1004 | Diana | ₹10,00,000 |

Delete `payments.db` to reset balances.

### Configuration (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `TEMPORAL_ADDRESS` | `localhost:7233` | Temporal server |
| `TEMPORAL_NAMESPACE` | `default` | Namespace |
| `TEMPORAL_TASK_QUEUE` | `payment-task-queue` | Queue shared by API and worker |
| `DATABASE_PATH` | `payments.db` | SQLite file |
| `APPROVAL_THRESHOLD` | `50000` | Above this, approval is required |
| `APPROVAL_TIMEOUT_SECONDS` | `600` | Auto-reject if no decision in time |
| `STEP_DELAY_SECONDS` | `2` | Artificial delay per activity so steps are visible |
| `PROCESSING_DELAY_SECONDS` | `10` | Duration of `process_payment` (window for the crash demo) |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS |

## 6. Start React

Requires Node 18+.

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to `http://localhost:8000`. Settings are in
`frontend/.env`.

## 7. Create a payment

In the dashboard pick sender **ACC-1001**, receiver **ACC-1002**, amount **1500** and click
**Create Payment**. The right panel shows the workflow live:

```text
Payment Created       ✓
Validation            ✓
Balance Check         ✓
Fraud Check           ⟳
Approval              –  (skipped, ≤ ₹50,000)
Payment Processing    -
Save Transaction      -
Notification          -
```

When it finishes you'll see a **Transaction ID** and the balances update. Click the workflow ID
(or "Full details") for the details page with the full event history.

With curl:

```bash
curl -X POST localhost:8000/api/payments -H "Content-Type: application/json" \
     -d '{"sender":"ACC-1001","receiver":"ACC-1002","amount":1500}'
curl localhost:8000/api/payments/payment-PAY-XXXXXXXX          # status
curl localhost:8000/api/payments/payment-PAY-XXXXXXXX/history  # history
```

Business failures you can trigger without any switch:

* **Insufficient funds**: send ₹10,000 from ACC-1003 (Charlie has ₹5,000).
* **Fraud flag**: send more than ₹5,00,000 from ACC-1004.

Both raise **non-retryable** errors. Temporal does not retry them, the workflow sends a failure
notification and ends as **Failed**.

## 8. Simulate an activity failure

Tick **Simulate Fraud Check Failure** and create a payment. Inside `fraud_check`:

```python
if payment.simulate_fraud_failure and attempt <= 2:
    raise RuntimeError("Fraud service unavailable (simulated, attempt N)")
```

Other switches:

* **Simulate Fraud Check Timeout**: attempt 1 sleeps 60s, but the workflow gave `fraud_check`
  a `start_to_close_timeout` of 5s. Temporal cancels it, records `activity StartToClose timeout`
  and retries. Attempt 2 succeeds. This demonstrates **activity timeout**.
* **Simulate Payment Failure**: `process_payment` fails on every attempt. Its retry policy
  allows 3 attempts. After the third, the workflow catches the error (**failure handling**),
  sends a failure notification and fails the workflow. No money moves.

## 9. Demonstrate retry

1. Tick **Simulate Fraud Check Failure** and create a payment.
2. Watch the *Fraud Check* row. It stays at ⟳ and the info column shows
   `retrying (attempt 2)`, then `attempt 3`, with the last error in red. The API reads this from
   the workflow's **pending activity** (`describe()`).
3. On attempt 3 it succeeds. The row shows **3 attempts, 2 retries** and the payment completes.
4. In the history you'll see `ACTIVITY_TASK_STARTED fraud_check (attempt 3) - previous failure: ...`.
   Temporal stores only the final attempt in history; it does not add an event per retry.

The workflow code has **no retry loop**. It only declares a policy:

```python
RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0, maximum_attempts=5)
```

## 10. Demonstrate worker restart / recovery

**A. Crash in the middle of an activity**

1. Create a normal payment (e.g. ₹1,000).
2. When the timeline shows **Payment Processing ⟳** (it takes 10s), **stop the worker**:
   Ctrl+C in its terminal, or with Docker run `docker kill payment-worker`.
3. The UI shows *"Worker offline"*. The workflow is still **RUNNING** in Temporal; nothing is lost.
   Because `process_payment` heartbeats every second and has `heartbeat_timeout=5s`, Temporal
   notices the dead worker and schedules attempt 2 (`last error: activity Heartbeat timeout`).
4. **Start the worker again**: `python -m app.temporal_worker` (Docker: `docker start payment-worker`).
5. The new worker replays the workflow history (validation, balance and fraud check are **not**
   re-run; their results come from history), runs `process_payment` attempt 2 and finishes. The
   `ledger` idempotency check guarantees the sender is debited once.

**B. Crash while waiting for approval**

1. Create a ₹60,000 payment. It stops at **Approval ⏸**.
2. Stop the worker (`docker kill payment-worker` with Docker).
3. Click **Approve Payment**. The API says *"worker offline - signal stored by Temporal"*.
   Signals are durable, so the server keeps the signal until a worker picks it up.
4. Start the worker (`docker start payment-worker`). The workflow resumes, sees the approval,
   and completes.

With Docker you can also restart Temporal itself (`docker compose restart temporal`). Running
workflows are persisted on its volume and continue afterwards.

(Both scenarios were verified while building this POC.)

## 11. Demonstrate the approval / waiting workflow

1. Create a payment over **₹50,000**, e.g. ₹75,000 from ACC-1004 (Diana) to ACC-1002.
2. After the fraud check, the workflow calls:
   ```python
   await workflow.wait_condition(lambda: self._decision is not None,
                                 timeout=timedelta(seconds=payment.approval_timeout_seconds))
   ```
   Status becomes **WAITING_APPROVAL**, approval **PENDING**. The history shows a
   `TIMER_STARTED` (the approval timeout). No worker thread is blocked while it waits.
3. Click **Approve Payment** (`POST /api/payments/{id}/approve`, which sends the `approve` signal)
   or **Reject Payment** (`reject` signal).
4. Approve: processing continues. Reject: a notification is sent and the payment ends as
   **REJECTED**. Temporal shows the workflow as *Completed* because rejection is a normal
   business outcome, not an error.
5. No decision within `APPROVAL_TIMEOUT_SECONDS` means the payment is auto-rejected (`TIMED_OUT`).
   Set it to e.g. `30` in `.env` and restart the API to try this.

A second approve/reject on the same payment returns **409**. The API first reads the workflow's
state through a query.

## 12. Inspect the workflow in Temporal UI

Open <http://localhost:8233> (or click **Open in Temporal UI ↗** on any payment).

* **Workflows list**: every payment as `payment-PAY-…`, with status Running / Completed / Failed.
* **A workflow → Event History**: the source of truth. Look for
  `ActivityTaskScheduled/Started/Completed`, `ActivityTaskFailed` (fraud flag / payment failure),
  `ActivityTaskTimedOut`, `TimerStarted`, `WorkflowExecutionSignaled` (approve/reject) and
  `WorkflowExecutionFailed`.
* **Pending Activities** (on a running workflow): the current attempt, last failure and next
  retry time. Watch it during the retry demo.
* **Input and Results**: the `PaymentInput` sent by FastAPI and the final `PaymentState`.
* **Queries tab**: run `get_status` to see the same data the React app shows.
* **Workers tab / Task Queue** `payment-task-queue`: shows whether a worker is polling. It
  disappears when you stop the worker.

---

## What this POC demonstrates

All of the following were run end to end against a local Temporal server while building the POC:

| Temporal capability | Where / how it shows up | Verified result |
|---|---|---|
| **Activity execution** | 6 activities run by the worker, orchestrated by `PaymentWorkflow` | ₹1,500 payment completed with a transaction ID, balances updated |
| **Activity retries** | "Simulate Fraud Check Failure": `RetryPolicy` with backoff, no retry code in the workflow | `fraud_check` failed twice and succeeded on attempt 3 |
| **Activity timeout** | "Simulate Fraud Check Timeout": 5s `start_to_close_timeout`; 5s `heartbeat_timeout` on `process_payment` | attempt 1 timed out (`StartToClose timeout`), attempt 2 succeeded |
| **Workflow status** | `describe()` + the `get_status` **Query**, polled by React every second | live step-by-step progress in the UI |
| **Workflow history** | `/api/payments/{id}/history` + Temporal UI; retry counts derived from history | full event list incl. failures, timers and signals |
| **Workflow failure handling** | non-retryable business errors (insufficient funds, fraud flag) vs retryable errors that exhaust `maximum_attempts=3` (payment failure); the workflow catches `ActivityError`, notifies, then fails | the workflow ended as **Failed** with a clear reason, and no money moved |
| **Worker restart recovery** | worker killed mid-`process_payment` and while waiting for approval | both workflows completed after restart; the sender was debited exactly once |
| **Signals + durable waiting** | `approve` / `reject` signals, `wait_condition` with a timeout timer | approve → completed, reject → REJECTED; a signal sent while the worker was offline was processed after restart |
| **Durability of the server itself** | dev server on a persistent volume | workflows still listed and completable after `docker compose restart` |

Deliberately **not** included (to keep it a POC): authentication, real payment integrations,
compensation/refund logic (mentioned in comments where it would go), multiple services, and
production Temporal deployment (a real setup would use a Temporal cluster or Temporal Cloud
with PostgreSQL/Cassandra, and TLS).
