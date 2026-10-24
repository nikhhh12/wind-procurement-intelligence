# Wind Procurement Intelligence

A full-stack operational analytics platform for a UK electricity utility's day-ahead power trading and procurement desk. It evaluates January 2026 national wind generation forecasts against actual metered generation from the Elexon BMRS Insights API and quantifies forecast error at half-hourly settlement resolution.

> **Trading & Operational Disclaimer:** This platform is designed for analytical backtesting, decision intelligence, and strategy review, not automated execution. The selected decision cutoff defaults to 10:00 UK time on the calendar day prior to delivery ($D-1$), aligning with EPEX SPOT / Nord Pool day-ahead auction submission workflows. The residual procurement panel uses an illustrative user-entered demand assumption; system demand is not sourced from Elexon in this demonstration.

---

## Key Features

- **Executive Analytics Dashboard:** Northstar Energy Intelligence UI with KPI cards (MAE, Forecast Bias, RMSE, WAPE, and Paired Period Coverage).
- **Daily Generation Composed Chart:** Visualizes daily forecast energy ($F_h \times 0.5\text{ h}$, blue area) vs. actual metered outturn ($A_i \times 0.5\text{ h}$, emerald line) with hover tooltips and interactive legends.
- **Auditable Settlement Period Explorer:** Full half-hourly inspection across all 1,488 settlement periods in January 2026. Features single-day filtering, 48-period pagination (Days 1–31), and a full-month view toggle.
- **Interactive Residual Procurement Calculator:** Illustrative day-ahead residual power requirement calculation ($\max(0, \text{Demand} - \overline{\text{Forecast}})$) for the selected delivery date.
- **Compliant CSV Data Export:** Full tabular download containing UTC timestamps, London local timestamps, settlement dates, settlement periods, forecast MW, actual MW, error MW, absolute error MW, forecast publication timestamps, and run metadata.
- **Optimized Elexon API Ingestion:** Single bulk streaming queries for `FUELHH` (`fuelType=WIND`) and `WINDFOR`, reducing upstream HTTP requests from 71 to 2 with in-memory TTL caching.
- **Strict Anti-Hindsight Selection:** Evaluates only forecast vintages published $\le 10:00$ UK time on $D-1$, picking the latest eligible revision. No future data leakage.

---

## Architecture & Technology Stack

```text
┌────────────────────────────────────────────────────────┐
│               Browser / Client (Port 8080)              │
│       React 18.3 (Vite 5.4, Recharts 2.15, Lucide)     │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP /api/
                           ▼
┌────────────────────────────────────────────────────────┐
│             Nginx Reverse Proxy & Static Host           │
└──────────────────────────┬─────────────────────────────┘
                           │ Proxy to backend:8000
                           ▼
┌────────────────────────────────────────────────────────┐
│           FastAPI Application (Port 8000)              │
│       Python 3.12, Uvicorn, Requests, In-Memory Cache   │
│     - Endpoint: /api/analysis                          │
│     - Endpoint: /api/health                            │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTPS Streaming Requests (x2)
                           ▼
┌────────────────────────────────────────────────────────┐
│             Elexon BMRS Insights API v1                │
│       https://data.elexon.co.uk/bmrs/api/v1            │
│     - FUELHH/stream (settlementDateFrom/To, WIND)      │
│     - WINDFOR/stream (publishDateTimeFrom/To)          │
└────────────────────────────────────────────────────────┘
```

- **Frontend:** React 18.3.1, Vite 5.4.11, Recharts 2.15.1, Lucide React 0.468.0, Vanilla CSS (Design tokens, glassmorphism, responsive grid).
- **Backend:** Python 3.12, FastAPI 0.115.6, Uvicorn 0.34.0, Requests 2.32.3, Pytest 8.3.4, HTTPX 0.28.1.
- **Reverse Proxy / Container:** Docker, Docker Compose, Nginx Alpine, Multi-stage builds.

---

## Repository Structure

```text
.
├── backend/
│   ├── Dockerfile             # Multi-stage Python API container with curl health check
│   ├── main.py                # Pure analysis engine, vintage selection, caching, REST API
│   ├── requirements.txt       # Pinned backend dependencies (FastAPI, Pytest, HTTPX)
│   └── tests/
│       ├── __init__.py
│       └── test_analysis.py   # 16 unit tests (cutoff, formulas, vintages, timeouts)
├── frontend/
│   ├── Dockerfile             # Multi-stage React Vite build + Nginx Alpine
│   ├── nginx.conf             # SPA fallback routing and /api/ reverse proxy
│   ├── index.html             # HTML5 entry with meta tags
│   ├── package.json           # Pinned npm dependencies
│   ├── package-lock.json      # Deterministic lockfile (71 KB)
│   └── src/
│       ├── main.jsx           # Dashboard UI, ComposedChart, pagination, CSV export
│       └── style.css          # Executive Northstar theme design tokens
├── docker-compose.yml         # Container orchestration with backend healthcheck
├── PROJECT_AUDIT_REPORT.md    # 15-section technical audit and remediation report
├── IMPLEMENTATION_SUMMARY.md  # Detailed engineering log, benchmarks, and checklist
├── VIDEO_SCRIPT.md            # Structured 10-minute demonstration video script
└── README.md                  # System documentation and instructions
```

---

## Quick Start with Docker (Recommended)

### Prerequisites
- Docker Engine $\ge 24.0$ or Docker Desktop with Compose plugin.

### Run Containers
```bash
docker compose up --build
```

The backend healthcheck verifies service readiness before Nginx proxies traffic.

- **Web Application:** [http://localhost:8080](http://localhost:8080)
- **API Health Check:** [http://localhost:8000/api/health](http://localhost:8000/api/health)
- **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

To stop the stack:
```bash
docker compose down
```

---

## Run Locally Without Docker

### 1. Backend Service
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Frontend Application
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
For local Vite development without Nginx, Vite proxies requests or uses `VITE_API_URL=http://localhost:8000`.

---

## Automated Test Suite

The test suite covers:
1. **Cutoff Inclusion:** Forecast published exactly at 10:00:00 UK on $D-1$ is accepted.
2. **Cutoff Exclusion:** Forecast published at 10:00:01 UK on $D-1$ is rejected.
3. **Latest Vintage Selection:** When multiple eligible forecasts exist (e.g. 02:30, 04:30, 07:30, 09:30), the 09:30 revision is selected.
4. **Missing Forecast Periods:** Half-hours lacking an eligible publication report `forecastMW: null` and increment `missingForecastPeriods`.
5. **Deduplication:** When duplicate actual records are received, the latest publication is preserved.
6. **Month Boundary Isolation:** 1 Jan uses 31 Dec cutoff; 31 Jan does not leak into 1 Feb.
7. **Timezone Normalization:** London clock time (BST/GMT) accurately mapped to UTC.
8. **Hourly-to-Half-Hourly Mapping:** Hourly forecasts map cleanly to pairs of settlement periods without doubling energy.
9. **Accuracy Metric Formulas:** Validates MAE, RMSE, Bias, and WAPE against synthetic datasets.
10. **Daily Energy Sums:** Validates $\text{MWh} = \text{MW} \times 0.5\text{ h}$.
11. **Upstream Error Handling:** Simulates Elexon timeouts and malformed JSON payloads.
12. **In-Memory Caching:** Verifies caching speedup and cache-bypass parameter (`refresh=true`).

### Running Tests Inside Docker
```bash
docker compose exec backend pytest -v
```

### Running Tests Locally on Host
```bash
pytest backend/tests -v
```

**Test Execution Result:** `16 passed in 0.41s`.

---

## API Specification

### `GET /api/health`
Returns service operational status.
- **Response:** `{"status": "ok", "service": "wind-procurement-intelligence", "cache_entries": 1}`

### `GET /api/analysis`
Fetches and computes forecast accuracy and settlement period details.

| Query Parameter | Type | Default | Description |
|---|---|---|---|
| `delivery_month` | string | `2026-01` | Delivery target month (`YYYY-MM`). |
| `cutoff_hour` | integer | `10` | Decision cutoff hour on $D-1$ in `Europe/London` (0–23). |
| `refresh` | boolean | `false` | If `true`, bypasses cache and re-fetches from Elexon BMRS. |

#### Response Schema
```json
{
  "month": "2026-01",
  "cutoffHourLondon": 10,
  "source": "Elexon BMRS (FUELHH actuals & WINDFOR forecasts)",
  "generatedAt": "2026-10-24T14:30:00Z",
  "counts": {
    "totalPeriods": 1488,
    "matchedPeriods": 1488,
    "missingForecastPeriods": 0,
    "missingActualPeriods": 0
  },
  "metrics": {
    "maeMW": 2126.12,
    "rmseMW": 2620.8,
    "biasMW": 1840.3,
    "wapePercent": 18.36
  },
  "daily": [
    {
      "date": "2026-01-01",
      "actualTotal": 368927.0,
      "forecastTotal": 471124.0,
      "periods": 48,
      "absErrorTotal": 102197.0
    }
  ],
  "rows": [
    {
      "startTime": "2026-01-01T00:00:00+00:00",
      "localTime": "2026-01-01T00:00:00+00:00",
      "settlementDate": "2026-01-01",
      "settlementPeriod": 1,
      "actualMW": 13756.0,
      "forecastMW": 19466.0,
      "publishTime": "2025-12-31T09:30:00+00:00",
      "errorMW": 5710.0,
      "absoluteErrorMW": 5710.0
    }
  ]
}
```

---

## Methodology & Calculation Rules

### 1. Decision Cutoff & Vintage Selection
Day-ahead power trading requires bids to be submitted prior to gate closure. For a delivery date $D$, the decision cutoff is set to 10:00 UK local time (`Europe/London`) on $D-1$:
$$\text{Cutoff}(D) = D - 1\text{ day at } 10:00:00\text{ Europe/London}$$
For any settlement interval on day $D$, the set of eligible forecast publications is:
$$\mathcal{F}_{\text{eligible}} = \{ f \in \text{WINDFOR} \mid \text{startTime}(f) \le t < \text{endTime}(f) \land \text{publishTime}(f) \le \text{Cutoff}(D) \}$$
The selected forecast is:
$$\hat{y}(t) = \arg\max_{f \in \mathcal{F}_{\text{eligible}}} \text{publishTime}(f)$$

### 2. Forecast Resolution Mapping
- Elexon `FUELHH` actuals are provided per 30-minute settlement period ($i = 1, \dots, 48$).
- Elexon `WINDFOR` forecasts are issued at 1-hour resolution. Each 1-hour forecast $F_h$ covers two half-hour settlement periods ($2h-1$ and $2h$).
- Energy total for the hour: $E_h = F_h \times 0.5\text{ h} + F_h \times 0.5\text{ h} = F_h \times 1.0\text{ h}$ (exact MWh conservation).

### 3. Metric Definitions
For $N$ paired settlement periods where both $\hat{y}_i$ (forecast) and $y_i$ (actual) are available:
- **Mean Absolute Error (MAE):**
  $$\text{MAE} = \frac{1}{N} \sum_{i=1}^N |\hat{y}_i - y_i| = 2,126.12\text{ MW}$$
- **Root Mean Squared Error (RMSE):**
  $$\text{RMSE} = \sqrt{\frac{1}{N} \sum_{i=1}^N (\hat{y}_i - y_i)^2} = 2,620.80\text{ MW}$$
- **Forecast Bias:**
  $$\text{Bias} = \frac{1}{N} \sum_{i=1}^N (\hat{y}_i - y_i) = +1,840.30\text{ MW}$$
  *(Positive bias indicates a persistent tendency to over-forecast wind generation).*
- **Weighted Absolute Percentage Error (WAPE):**
  $$\text{WAPE} = \frac{\sum_{i=1}^N |\hat{y}_i - y_i|}{\sum_{i=1}^N y_i} \times 100 = 18.36\%$$

---

## Performance Optimization Results

| Metric | Original Implementation | Optimized Implementation | Improvement |
|---|---|---|---|
| Upstream HTTP Calls | 71 sequential calls | 2 bulk stream queries | **97.2% reduction** |
| Cold API Latency | 27.8 seconds | 2.44 seconds | **11.4x faster** |
| Cached API Latency | N/A (no caching) | 0.10 seconds | **278x faster** |
| Matched Coverage | 1,488 / 1,488 (100%) | 1,488 / 1,488 (100%) | 100% parity |
| Error Metrics (MAE) | 2,126.12 MW | 2,126.12 MW | Identical to 2 decimal places |

---

## Known Limitations

1. **Illustrative Residual Demand:** System demand in the residual procurement panel is user-entered; real production requires actual National Grid ESO demand data (INDO/ITSDO).
2. **Single In-Memory Process Cache:** The current cache uses an in-memory TTL dictionary. Multi-replica cloud deployments should use a shared Redis cache.
3. **Public Deployment & Git Initialization:** In accordance with instructions, Git initialization and public deployment are awaiting explicit user approval.

---

## AI-Assisted Development Disclosure

Portions of this codebase, test suites, architecture audit, and documentation were developed with assistance from Google Antigravity (Advanced Agentic AI). All API queries, numerical formulas, and visual behaviors were verified against live Elexon BMRS data.

---

## Final Submission Checklist

- [x] ComposedChart renders both forecast area and actual generation line.
- [x] Backend response latency $\le 3$ seconds with bulk queries and caching.
- [x] Settlement periods view provides full navigation across all 1,488 intervals.
- [x] Automated test suite (16 tests) passing cleanly via `pytest`.
- [x] Frontend dependencies pinned with committed `package-lock.json`.
- [x] Docker Compose health check configured and verified.
- [x] CSV export includes complete delivery and cutoff metadata.
- [ ] Initialize Git repository (`git init`), create commit, and push to anonymous GitHub repository (Awaiting User Approval).
- [ ] Deploy to public cloud platform (Awaiting User Approval).
- [ ] Record 10-minute video walkthrough following `VIDEO_SCRIPT.md`.
