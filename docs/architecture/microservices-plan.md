# TradeCore v2 — Microservices Architecture & Build Plan

> Status: **Design / not yet built**. This document is the source of truth for the
> rewrite. Update it as services are built and decisions change.
> Last updated: 2026-06-17.

---

## 1. Why we are doing this

TradeCore v1 is a single FastAPI monolith: data ingestion, indicators, Hawkes,
sentiment, signal logic, risk, execution, journaling, the event log, and the API
all live in one process sharing one `app_state` and one database session factory.

It works, but:

- **Hard to test in isolation** — a change to the risk guard drags in the whole
  app (DB, scheduler, WebSocket) to exercise.
- **Hard to upgrade** — no clean seams; everything imports everything.
- **Hard to reason about** — one failure mode (a bad migration, a hung Claude
  call) can take down unrelated functionality.

**Goal:** rebuild as a set of small, independently testable, independently
deployable services — and build them **one at a time, maturing each before
starting the next**. Each service does one thing, owns its data, and talks to
the rest only through well-defined events and REST contracts.

---

## 2. Architecture decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Migration path | **Greenfield rewrite** | New repo structure, port logic service-by-service. Clean seams from day one. |
| Inter-service comms | **Event bus (NATS JetStream) + REST** | Trading is event-driven (bar → indicators → signal → decision → risk → fill). Async bus decouples producers/consumers and gives durable replay + an audit trail. REST for synchronous queries (history, config). |
| Data ownership | **Shared TimescaleDB, schema-per-service** | One Timescale instance (keeps hypertables, one ops surface for a single-node setup). Each service owns its own Postgres **schema** and is the only writer to it. No cross-service writes; read other services' data via their REST/events, not their tables. |
| Bus implementation | **NATS JetStream** (fallback: Redis Streams) | Single lightweight binary, durable streams, consumer groups, replay, subject wildcards. v1 scaffold deliberately excluded Redis; NATS keeps that clean and is purpose-built for messaging. |
| Repo layout | **Monorepo** | Solo/small team; shared contracts and libs are far easier to version in one repo. Each service still builds/tests/deploys independently. |
| Language | **Python 3.13 + FastAPI + async SQLAlchemy** per service | Reuse v1 logic and the team's existing stack. |

### The golden rule of data ownership
A service may **write only to its own schema**. To use another service's data it
either (a) subscribes to that service's events, or (b) calls that service's REST
API. Never reach into another schema's tables directly. This is what makes a
service independently upgradeable.

---

## 3. Target topology

```
                                 ┌──────────────┐
   Binance/CCXT/yfinance ──────► │ market-data  │ ─┐  md.bars.* / md.ticks.*
                                 └──────────────┘  │
                                                    ▼ (NATS JetStream)
        ┌───────────────┬───────────────┬──────────┴───────┬──────────────┐
        ▼               ▼               ▼                  ▼              ▼
  ┌───────────┐  ┌─────────────┐  ┌───────────┐    ┌────────────┐  ┌───────────┐
  │ indicator │  │microstructure│ │ sentiment │    │  activity  │  │validation │
  │           │  │  (Hawkes)    │ │           │    │ (audit log)│  │ (on-demand)│
  └─────┬─────┘  └──────┬──────┘  └─────┬─────┘    └──────┬─────┘  └───────────┘
        │ ind.composite │ hawkes.*      │ sent.*          │ (consumes ALL subjects)
        └───────┬───────┴───────────────┘                 │
                ▼                                          │
          ┌───────────┐  sig.zone.*                        │
          │  signal   │ ─────────────┐                     │
          └───────────┘              ▼                     │
                              ┌─────────────┐ dec.proposed │
                              │  decision   │ ─────────┐    │
                              │ (rules/agent)│         ▼    │
                              └─────────────┘   ┌───────────┐ risk.intent
                                                │   risk    │ ──────────┐
                                                └───────────┘           ▼
                                                              ┌──────────────┐ exec.trade.*
                                                              │  execution   │ ──────┐
                                                              │ (paper/live) │       ▼
                                                              └──────────────┘  ┌──────────────┐
                                                                                │journal-feedback│
                                                                                └──────────────┘
                                                                                   │ fb.updated.*
                                                                                   ▼ (back to decision)

   ┌──────────┐   REST + WS    ┌──────────┐
   │ frontend │ ◄────────────► │ gateway  │ ◄── REST to every service, WS fanout, auth,
   └──────────┘                │ /control │     kill-switch, trading-mode, strategy CRUD
                               └──────────┘
```

---

## 4. Service catalog

Each service: **one responsibility**, **one schema it owns**, the **events it
consumes/publishes**, its **REST surface**, and what it ports from v1.

### 4.1 `market-data`
- **Responsibility:** ingest OHLCV (CCXT/Binance US), ticks (Binance WS), stock bars (yfinance). Normalize, dedup, persist, publish.
- **Owns schema:** `market` (`ohlcv`, `tick_trades`).
- **Publishes:** `md.bars.{exchange}.{symbol}.{tf}`, `md.ticks.{venue}.{symbol}`.
- **Consumes:** `ctl.watchlist` (which symbols to stream).
- **REST:** `GET /ohlcv`, `GET /ohlcv/count`, `POST /sync`.
- **Ports from v1:** `data_ingestion.py`, `binanceus_ws.py`, `exchange_client.py`, `stock_feed.py`.

### 4.2 `indicator`
- **Responsibility:** compute technical indicators + weighted composite per bar.
- **Owns schema:** `indicators` (`indicator_snapshots`, `composite_scores`).
- **Consumes:** `md.bars.*`.
- **Publishes:** `ind.composite.{symbol}`.
- **REST:** `GET /indicators?symbol=`.
- **Ports from v1:** `indicator_engine.py`, `aggregator.py`.

### 4.3 `microstructure` (Hawkes OFI)
- **Responsibility:** fit bivariate Hawkes on ticks, compute pressure + regime + forecast.
- **Owns schema:** `hawkes` (`hawkes_params`).
- **Consumes:** `md.ticks.*`.
- **Publishes:** `hawkes.pressure.{symbol}`, `hawkes.regime.{symbol}`.
- **REST:** `GET /pressure`, `GET /forecast`.
- **Ports from v1:** `hawkes_ofi.py`, `routers/hawkes.py`, `refit_hawkes_job`.

### 4.4 `sentiment`
- **Responsibility:** ingest news/social, score sentiment + price-impact via Claude.
- **Owns schema:** `content` (`news_items`, `social_posts`, `feed_sources`, `sentiment_cache`).
- **Consumes:** —
- **Publishes:** `sent.score.{symbol}`, `content.news`, `content.social`.
- **REST:** `GET /news`, `GET /social`, `POST /refresh`, sources CRUD, `GET /impact`.
- **Ports from v1:** `sentiment_agent.py`, `news_aggregator.py`, `social_aggregator.py`, `claude_auth.py`.
- **Constraints (carry over):** Claude proxy key from `CLAUDE_PROXY_API_KEY` env, never stored; one user message per call, no system prompt.

### 4.5 `signal`
- **Responsibility:** fuse composite + Hawkes pressure + sentiment into an ensemble; classify zone; apply regime gate.
- **Owns schema:** `signal` (`signals`).
- **Consumes:** `ind.composite.*`, `hawkes.pressure.*`, `hawkes.regime.*`, `sent.score.*`.
- **Publishes:** `sig.zone.{symbol}`.
- **REST:** `GET /signals`.
- **Ports from v1:** `signal_ensemble.py`, `rule_engine.py` (zone parts).

### 4.6 `decision`
- **Responsibility:** turn a signal into a proposed action — deterministic rules **or** the Claude trader agent (`decision_mode`).
- **Owns schema:** `decision` (proposals log).
- **Consumes:** `sig.zone.*`, `exec.position.*`, `fb.updated.*` (for agent context).
- **Publishes:** `dec.proposed.{symbol}`.
- **REST:** `GET /decisions`.
- **Ports from v1:** `rule_engine.py`, `trader_agent.py`.

### 4.7 `risk`
- **Responsibility:** the hard, unbypassable safety layer — vol-sizing, stop/target, exposure caps, drawdown breaker. Turns a proposal into a sized order intent or a veto.
- **Owns schema:** `risk` (limits, peak-equity high-water marks).
- **Consumes:** `dec.proposed.*`, `exec.position.*`, `md.bars.*` (for ATR/price).
- **Publishes:** `risk.intent.{symbol}`, `risk.veto.{symbol}`.
- **REST:** `GET /limits`, `PUT /limits`.
- **Ports from v1:** `risk_guard.py`.

### 4.8 `execution`
- **Responsibility:** fill order intents — paper broker (sim) and live broker (CCXT). Track trades + positions.
- **Owns schema:** `execution` (`trades`, `positions`).
- **Consumes:** `risk.intent.*`, `ctl.mode`, `ctl.killswitch`.
- **Publishes:** `exec.trade.{mode}.{symbol}`, `exec.position.{mode}.{symbol}`.
- **REST:** `GET /positions`, `GET /trades`, `GET/PUT /account`.
- **Ports from v1:** `execution.py`, `paper_broker.py`.

### 4.9 `journal-feedback`
- **Responsibility:** journal closed trades with decision context; aggregate per-regime/per-mode expectancy; publish feedback for the agent.
- **Owns schema:** `journal` (`trade_journal`).
- **Consumes:** `exec.trade.*` (enriched with regime/decision context via event metadata).
- **Publishes:** `fb.updated.{mode}`.
- **REST:** `GET /performance`.
- **Ports from v1:** `feedback.py`, `TradeJournal`, `compute_performance_feedback_job`.

### 4.10 `validation`
- **Responsibility:** walk-forward / purged-CV backtest harness + OOS pass/fail gate. On-demand (REST), not on the hot path.
- **Owns schema:** `validation` (run results).
- **Consumes:** reads `market` data via market-data REST.
- **Publishes:** `val.completed` (optional).
- **REST:** `POST /run`, `POST /validate`.
- **Ports from v1:** `backtest_runner.py`, `validation.py`.

### 4.11 `activity` (event log / audit)
- **Responsibility:** subscribe to **every** subject on the bus, persist to the event log, serve the Activity tab + WS fanout for it.
- **Owns schema:** `events` (`event_log` hypertable).
- **Consumes:** `>` (all subjects).
- **Publishes:** — (re-broadcasts to UI WS).
- **REST:** `GET /events`, `GET /events/categories`.
- **Ports from v1:** `event_log.py`, `routers/events.py`.

### 4.12 `gateway` / `control`
- **Responsibility:** single front door for the frontend — reverse-proxy/aggregate REST to services, WS fanout, **auth**, and global control state (kill switch, trading mode, strategy CRUD, watchlist).
- **Owns schema:** `control` (`controls`, `strategies`, `watched_symbols`).
- **Consumes:** —
- **Publishes:** `ctl.killswitch`, `ctl.mode`, `ctl.watchlist`, `ctl.strategy`.
- **REST:** `/control/*`, `/strategy/*`, `/watchlist/*`, plus proxied routes.
- **Ports from v1:** `control.py`, `strategy.py`, `watchlist.py`, `main.py` lifespan/state.

---

## 5. Event taxonomy

Subjects are `namespace.entity.{routing...}`. Wildcards: `*` one token, `>` all.

| Subject | Payload (core fields) | Producer |
|---|---|---|
| `md.bars.{ex}.{sym}.{tf}` | ts, ohlcv | market-data |
| `md.ticks.{venue}.{sym}` | ts, price, qty, side | market-data |
| `ind.composite.{sym}` | ts, score, components | indicator |
| `hawkes.pressure.{sym}` | ts, pressure, λ_buy, λ_sell | microstructure |
| `hawkes.regime.{sym}` | ts, regime, branching | microstructure |
| `sent.score.{sym}` | ts, score, source | sentiment |
| `sig.zone.{sym}` | ts, zone, score | signal |
| `dec.proposed.{sym}` | ts, action, size_fraction, confidence, decision_mode, reason | decision |
| `risk.intent.{sym}` | ts, action, qty_usdt, stop, target | risk |
| `risk.veto.{sym}` | ts, reason | risk |
| `exec.trade.{mode}.{sym}` | ts, side, price, qty, pnl, + decision context | execution |
| `exec.position.{mode}.{sym}` | ts, open/closed, entry, qty | execution |
| `fb.updated.{mode}` | per-regime expectancy summary | journal-feedback |
| `ctl.killswitch` / `ctl.mode` / `ctl.watchlist` / `ctl.strategy` | new state | gateway |

**Envelope (every event):** `{ id, ts, subject, producer, schema_version, payload }`.
Defined once in `packages/contracts`. The `activity` service persists the envelope verbatim.

**Decision-context propagation:** so the journal can attribute a trade to the regime/agent that caused it, the context (regime, pressure, confidence, decision_mode) rides along the `dec.proposed → risk.intent → exec.trade` chain in the envelope metadata. No service has to query backwards.

---

## 6. Repository structure (monorepo)

```
tradecore/
├── services/
│   ├── market-data/       app/  tests/  Dockerfile  pyproject.toml  README.md
│   ├── indicator/
│   ├── microstructure/
│   ├── sentiment/
│   ├── signal/
│   ├── decision/
│   ├── risk/
│   ├── execution/
│   ├── journal-feedback/
│   ├── validation/
│   ├── activity/
│   └── gateway/
├── packages/              # shared, versioned libraries (installed by each service)
│   ├── contracts/         # event envelope + payload pydantic models + subject names
│   ├── libbus/            # NATS JetStream client wrapper: publish(), subscribe(), consumer groups
│   ├── libdb/             # async engine factory, Base, per-schema migration helper
│   └── libobs/            # structlog config + emit_event() helper (publishes to bus)
├── frontend/              # React + Vite (mostly unchanged; points at gateway)
├── deploy/
│   ├── docker-compose.yml         # full stack: nats, timescaledb, all services, frontend
│   ├── docker-compose.dev.yml     # infra only (nats + db) for local single-service dev
│   └── nats/                      # JetStream config
├── migrations/            # one Alembic env per schema (or per service), versioned independently
├── Makefile               # up, test, lint, new-service scaffold
└── docs/architecture/microservices-plan.md   # this file
```

**Per-service standard layout:**
```
services/<name>/
├── app/
│   ├── main.py            # FastAPI app + lifespan (connect bus, db)
│   ├── config.py          # pydantic-settings, env only
│   ├── handlers/          # bus event handlers (one per subscribed subject)
│   ├── service.py         # the pure domain logic (ported, unit-tested, no I/O)
│   ├── repo.py            # DB access for THIS service's schema only
│   └── routes.py          # REST endpoints
├── tests/                 # unit (pure logic) + contract (event in/out) + integration
├── Dockerfile
├── pyproject.toml
└── README.md              # responsibility, events, REST, maturity checklist
```

---

## 7. Definition of "mature" (per service)

A service is **done** — i.e. we can start the next one — only when **all** are true:

1. **Pure core extracted** — domain logic is a pure module with no I/O, fully unit-tested (the v1 work already gives us this for risk, validation, signal, feedback, agent).
2. **Contract tests** — given a sample input event, it emits the correct output event matching the `contracts` schema.
3. **Integration test** — runs against a real NATS + Timescale (docker-compose.dev), consumes a real event, persists, publishes.
4. **Owns only its schema** — verified: no writes outside its schema.
5. **Health + observability** — `/health` endpoint; emits lifecycle events to the bus (so `activity` shows it); structured logs.
6. **Dockerized** — builds, runs in `docker-compose.yml`, has a healthcheck.
7. **README** — responsibility, subjects in/out, REST, env vars, maturity checklist ticked.
8. **CI green** — its own test job passes in the pipeline.

---

## 8. Build order

Dependency- and value-ordered. Build, mature (Section 7), then move on.

| # | Service | Why this order |
|---|---|---|
| 0 | **Platform foundation** | Monorepo, `contracts`, `libbus`, `libdb`, `libobs`, `docker-compose.dev` (NATS + Timescale), Makefile, CI skeleton. Nothing else can be built without this. |
| 1 | **market-data** | Everything downstream needs bars/ticks. First real service end-to-end proves the bus + db + contract pattern. |
| 2 | **activity** | Stand up the audit log early — then while building every later service you can *watch its events land*. Doubles as your integration-test oracle. |
| 3 | **indicator** | Simple consumer of `md.bars.*`; validates the consume→compute→publish loop. |
| 4 | **microstructure** | Consumer of `md.ticks.*`; the Hawkes math is already isolated and tested. |
| 5 | **signal** | Fuses indicator + hawkes; introduces multi-source consumption + the regime gate. |
| 6 | **risk** | Pure, already fully tested (`risk_guard.py`) — fast to extract, high safety value. Can be exercised with synthetic intents before execution exists. |
| 7 | **execution** | Paper broker first. Now `sig → dec(stub) → risk → exec` can run end-to-end in paper. |
| 8 | **decision** | Rules first, then port the Claude agent. Slots between signal and risk. |
| 9 | **journal-feedback** | Consumes fills, closes the learning loop back into decision. |
| 10 | **validation** | On-demand, off the hot path; port the tested harness. Gate strategies before they go live. |
| 11 | **sentiment** | Enriches signals; optional to the core loop, so later. |
| 12 | **gateway/control + frontend** | Tie it together for the UI; auth; global control. Frontend repointed from the v1 monolith to the gateway. |

**Milestone after #7:** a complete paper-trading loop running across services
(market-data → indicator/microstructure → signal → decision-stub → risk →
execution), fully visible in `activity`. That's the first "it lives" moment.

---

## 9. Testing strategy

- **Unit (pure):** the domain core of each service. This is where the bulk of the
  v1 test suite (~120 tests for risk, validation, signal, feedback, agent) ports
  over directly — the logic doesn't change, only its packaging.
- **Contract:** input event fixture → assert output event matches `contracts`
  schema. Catches breaking changes at the seam, not in production.
- **Integration:** docker-compose.dev (NATS + Timescale) + the one service;
  publish a real event, assert DB row + published event.
- **End-to-end (later):** a `scenarios/` harness that feeds synthetic bars into
  market-data and asserts a paper trade comes out the far end.

Each service's tests run independently — no more "spin up the whole app to test
the risk guard."

---

## 10. Deployment & ops

- **`docker-compose.yml`** — nats, timescaledb, all services, frontend. One `make up`.
- **`docker-compose.dev.yml`** — just nats + timescaledb, for working on a single service locally.
- **Migrations** — per-schema Alembic envs; each service migrates its own schema on startup (or a dedicated migrate job). No service touches another's migrations.
- **Config** — env only, per service (`pydantic-settings`). Secrets (`CLAUDE_PROXY_API_KEY`, exchange keys) never committed, never logged.
- **CI** — matrix over services: lint + unit + contract per service; integration on a compose-backed job. A service can ship without rebuilding others.
- **Observability** — every service emits lifecycle + domain events to the bus → `activity` persists them → Activity tab shows the whole system. structlog JSON to stdout for container logs.

---

## 11. What carries over from v1 (already built & tested)

These pure modules port almost verbatim into their services' `service.py`:

| v1 module | → service | Tests |
|---|---|---|
| `risk_guard.py` | risk | 31 |
| `validation.py` | validation | 26 |
| `signal_ensemble.py` | signal | 16 |
| `trader_agent.py` | decision | 20 |
| `feedback.py` | journal-feedback | 13 |
| `event_log.py` | activity | 10 |
| `hawkes_ofi.py` | microstructure | (existing) |
| `indicator_engine.py`, `aggregator.py` | indicator | (existing) |
| `backtest_runner.py` | validation | (existing) |

The hard logic is done and proven. The rewrite is mostly **re-packaging proven
pure modules behind event handlers and per-service schemas** — not reinventing.

---

## 12. Risks & open questions

- **Distributed debugging** — a bug now spans services. Mitigation: `activity`
  audit log with correlation IDs in the envelope (carry a `trace_id` from the
  originating bar through to the fill).
- **Event ordering / replay** — JetStream gives per-subject ordering and replay;
  design handlers to be idempotent (dedup on event `id`).
- **Schema-per-service in one DB** — discipline, not enforcement. Add a CI check
  that each service's `repo.py` only references its own schema.
- **Latency budget** — extra hops (bus + serialization) vs the monolith's
  in-process calls. For a 5-min cycle this is negligible; note it if we ever go
  high-frequency.
- **Open:** auth model for the gateway (API key vs session) — decide before #12.
- **Open:** do we keep the v1 monolith running in parallel during the rewrite, or
  is this a clean cutover? (Greenfield implies cutover at the end; confirm.)

---

## 13. Next action

Build **#0 Platform foundation**: scaffold the monorepo, write `packages/contracts`
(event envelope + the subject names in Section 5), `libbus` (NATS wrapper),
`libdb`, `libobs`, and `docker-compose.dev.yml` (NATS + Timescale). Then **#1
market-data** as the first vertical slice to prove the pattern end-to-end.
