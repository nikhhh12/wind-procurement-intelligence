# Wind Procurement Intelligence

A full-stack operational analytics platform for a UK electricity utility's day-ahead power trading and procurement desk. It evaluates multi-month national wind generation forecasts (October 2025 through March 2026) from the Elexon BMRS Insights API (`WINDFOR`) against metered outturn actuals (`FUELHH`) and quantifies forecast error at half-hourly settlement resolution.

> **Trading & Operational Disclaimer:** This platform is designed for analytical backtesting, decision intelligence, and strategy review, not automated execution. The selected decision cutoff defaults to 10:00 UK time on the calendar day prior to delivery ($D-1$), aligning with EPEX SPOT / Nord Pool day-ahead auction submission workflows, and supports selectable 08:00, 10:00, 12:00, and 16:00 UK cutoffs. The residual procurement panel uses an illustrative user-entered demand assumption; system demand is not sourced from Elexon in this demonstration.

---

## Dashboard Preview

```text
+-------------------------------------------------------------------------------------------------------+
|  Northstar Energy Intelligence        [ Delivery Month: 2026-01 v ]  [ Cutoff: 10:00 UK v ]  [Export] |
|-------------------------------------------------------------------------------------------------------|
|  [ Mean Absolute Error ]   [ Forecast Bias ]         [ RMSE ]                  [ Matched Periods ]    |
|       2,126 MW                 +1,840 MW             2,621 MW                     1,488 / 1,488       |
|  Typical half-hour miss    Tends to over-forecast    Penalises larger misses   100% paired coverage   |
|-------------------------------------------------------------------------------------------------------|
|  Daily Wind Generation (Forecast Area vs Actual Line)               [ 48 Periods / Day View ]         |
|  [~~~~~~~~~~~~~~~~~~~~~ ComposedChart: Area (Forecast) & Line (Actual) ~~~~~~~~~~~~~~~~~~~~~~~~~~~~]  |
|-------------------------------------------------------------------------------------------------------|
|  Settlement Period Review (Single Day / All Month)   |  Residual Procurement Planner (Illustrative)   |
|  Time (UK) | Forecast | Actual | Error               |  Expected Demand: 32,000 MW (User Input)       |
|  00:00     | 19,466   | 13,756 | +5,710 MW           |  - Mean Wind:     19,466 MW                    |
|  00:30     | 19,466   | 14,120 | +5,346 MW           |  = Indicative Residual: 12,534 MW              |
+-------------------------------------------------------------------------------------------------------+
```

> **Adding a Screenshot:** To embed a high-resolution screenshot of the running dashboard in this repository:
> 1. Launch the application via `docker compose up --build` and navigate to `http://localhost:8080`.
> 2. Capture a full-page screenshot of the dashboard.
> 3. Save the image file as `docs/dashboard.png` (or `assets/dashboard.png`).
> 4. Add the following Markdown snippet below this callout:
>    ```markdown
>    ![Wind Procurement Intelligence Dashboard](docs/dashboard.png)
>    ```
> *(No screenshot image file is currently tracked in Git to maintain a clean repository footprint.)*

---

## Key Features

- **Multi-Month Historical Coverage:** Evaluates six consecutive delivery months (**October 2025 through March 2026**), dynamically discoverable via `/api/supported-months`.
- **Selectable Decision Cutoffs:** Supports **08:00, 10:00, 12:00, and 16:00 UK local time** on $D-1$, mirroring power desk submission deadlines and gate closures.
- **Executive Analytics Dashboard:** Northstar Energy Intelligence UI with KPI cards (MAE, Forecast Bias, RMSE, WAPE, and Matched Periods).
- **Daily Generation Composed Chart:** Visualizes daily forecast energy ($F_h \times 0.5\text{ h}$, blue area) vs. actual metered outturn ($A_i \times 0.5\text{ h}$, emerald line) using Recharts `ComposedChart` with tooltips and interactive legends.
- **Dynamic Settlement Period Explorer:** Adapts to month length (1,344 to 1,490 settlement periods). Features single-day dropdown filtering, 48-period pagination navigation (Day $X$ of $Y$ with Prev/Next buttons), and a full-month view toggle.
- **Interactive Residual Procurement Calculator:** Illustrative day-ahead residual power requirement calculation ($\max(0, \text{Demand} - \overline{\text{Forecast}})$) for the selected delivery date.
- **Compliant CSV Data Export:** Full tabular download containing UTC timestamps, London local timestamps, settlement dates, settlement periods, forecast MW, actual MW, error MW, absolute error MW, forecast publication timestamps, and run metadata.
- **Optimized Elexon API Ingestion:** Single bulk streaming queries for `FUELHH` (`fuelType=WIND`) and `WINDFOR`, reducing upstream HTTP requests from 71 to 2 with in-memory TTL caching.
- **Strict Anti-Hindsight Vintage Selection:** Evaluates only forecast vintages published $\le \text{Cutoff}$ on $D-1$, picking the latest eligible revision. No future data leakage.
- **Daylight-Saving-Time-Safe Interval Alignment:** UTC-based half-hourly forecast expansion ensures monotonic time steps and eliminates timezone fold/ambiguity defects during UK clock changes.

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
│     - Endpoint: /api/health                            │
│     - Endpoint: /api/supported-months                  │
│     - Endpoint: /api/analysis?month=YYYY-MM&cutoff=HH  │
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
│       └── test_analysis.py   # 24 unit & regression tests (cutoffs, formulas, vintages, DST, caching)
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
- **Supported Months:** [http://localhost:8000/api/supported-months](http://localhost:8000/api/supported-months)
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

The 24-test suite verifies all core analytical requirements, boundary conditions, and edge cases:

1. **`test_health_check`:** Verifies service health endpoint responds with HTTP 200 `ok`.
2. **`test_cutoff_inclusion_boundary`:** Forecast published at exactly 10:00:00 UK on $D-1$ is eligible.
3. **`test_cutoff_exclusion_boundary`:** Forecast published at 10:00:01 UK on $D-1$ (1 second late) is excluded.
4. **`test_latest_eligible_vintage_selection`:** Selects latest eligible publication among multiple pre-cutoff vintages.
5. **`test_missing_forecast_period`:** Reports `null` for missing forecasts without falsifying accuracy metrics.
6. **`test_missing_actual_period`:** Missing actuals are excluded from paired error metrics.
7. **`test_duplicate_actual_publications`:** Deduplicates actuals by delivery period, retaining latest publication.
8. **`test_month_boundary_handling`:** Month grid bounds are strictly 1st to last day; 1 Jan uses 31 Dec cutoff.
9. **`test_timezone_conversion`:** UK local cutoff hour is correctly mapped to UTC across BST/GMT.
10. **`test_hourly_to_half_hourly_expansion`:** Hourly WINDFOR forecast maps to two 30-minute intervals without energy doubling.
11. **`test_accuracy_metric_formulas`:** Mathematical validation of MAE, RMSE, Forecast Bias, and WAPE formulas.
12. **`test_daily_energy_calculation`:** Validates half-hourly MW conversion to MWh ($E = \text{MW} \times 0.5$).
13. **`test_upstream_elexon_timeout`:** Upstream network timeout raises HTTP 502 with diagnostic detail.
14. **`test_upstream_malformed_response`:** Malformed JSON from Elexon raises HTTP 502.
15. **`test_query_parameter_validation`:** Rejects invalid month format and out-of-bounds cutoffs with HTTP 422.
16. **`test_supported_months_endpoint`:** Validates `/api/supported-months` returns list and default month.
17. **`test_unsupported_month_rejection`:** Out-of-range month returns HTTP 400 Bad Request with supported list.
18. **`test_february_2026_grid_calculation`:** February 2026 constructs exactly 28 days = 1,344 half-hourly periods.
19. **`test_december_2025_grid_calculation`:** December 2025 constructs exactly 31 days = 1,488 half-hourly periods.
20. **`test_month_selection_cutoff_continuity`:** Cutoff continuity holds across month boundaries (Feb 1 uses Jan 31 cutoff).
21. **`test_caching_behavior`:** Confirms cache hit avoids redundant network requests to Elexon.
22. **`test_autumn_clock_change_forecast_period_keys`:** Verifies UTC expansion produces distinct settlement period keys during UK autumn clock fallback, preventing fold reset bugs.
23. **`test_october_clock_change_matching_and_no_missing_intervals`:** Verifies SP 4, SP 5, and SP 6 on 26 Oct 2025 all receive valid forecasts without missing intervals.
24. **`test_cutoff_differentiation_between_12_and_16`:** Confirms 12:00 UK and 16:00 UK cutoffs select distinct forecast vintages when afternoon updates are published on $D-1$.

### Running Tests Inside Docker
```bash
docker compose exec backend pytest -v
```

### Running Tests Locally on Host
```bash
pytest backend/tests -v
```

**Verified Test Result:** `24 passed, 1 warning in 0.30s` (in Docker container) / `24 passed in 0.65s` (on host).

---

## API Specification

### `GET /api/health`
Returns service operational status.
- **Response:** `{"status": "ok", "service": "wind-procurement-intelligence"}`

### `GET /api/supported-months`
Returns the list of delivery months supported by this service.
- **Response:**
  ```json
  {
    "supportedMonths": ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"],
    "defaultMonth": "2026-01"
  }
  ```

### `GET /api/analysis`
Fetches and computes forecast accuracy and settlement period details for the selected delivery month and decision cutoff.

| Query Parameter | Type | Default | Description |
|---|---|---|---|
| `month` | string | `2026-01` | Delivery target month (`YYYY-MM`). Must be in supported months list. |
| `cutoff_hour` | integer | `10` | Decision cutoff hour on $D-1$ in `Europe/London` (0–23). Supported UI options: 8, 10, 12, 16. |
| `refresh` | boolean | `false` | If `true`, bypasses cache and re-fetches from Elexon BMRS. |

#### Response Schema (Illustrative Example for January 2026 at 10:00 UK Cutoff)
```json
{
  "month": "2026-01",
  "cutoffHourLondon": 10,
  "source": "Elexon BMRS Insights API",
  "generatedAt": "2026-10-25T01:00:00+00:00",
  "counts": {
    "actualRecords": 1488,
    "forecastRecords": 16864,
    "pairedPeriods": 1488,
    "missingForecastPeriods": 0,
    "expectedPeriods": 1488
  },
  "metrics": {
    "maeMW": 2126.12,
    "rmseMW": 2620.80,
    "biasMW": 1840.30,
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
  ],
  "methodology": "January 2026 delivery periods are evaluated in UK local time. For each half-hourly delivery period, the latest WINDFOR publication available by the configured cutoff on the previous UK calendar day is selected..."
}
```

---

## Methodology & Calculation Rules

### 1. Decision Cutoff & Vintage Selection
Day-ahead power trading requires bids to be submitted prior to gate closure. For a delivery date $D$, the decision cutoff is set to the configured hour in UK local time (`Europe/London`) on $D-1$:
$$\text{Cutoff}(D) = D - 1\text{ day at } \text{cutoff\_hour}:00:00\text{ Europe/London}$$
For any settlement interval on day $D$, the set of eligible forecast publications is:
$$\mathcal{F}_{\text{eligible}} = \{ f \in \text{WINDFOR} \mid \text{startTime}(f) \le t < \text{endTime}(f) \land \text{publishTime}(f) \le \text{Cutoff}(D) \}$$
The selected forecast is the latest publication released prior to the cutoff:
$$\hat{y}(t) = \arg\max_{f \in \mathcal{F}_{\text{eligible}}} \text{publishTime}(f)$$

### 2. Forecast Resolution Mapping & UTC Arithmetic
- Elexon `FUELHH` actuals are provided per 30-minute settlement period ($i = 1, \dots, 48$ on standard days).
- Elexon `WINDFOR` forecasts are issued at 1-hour resolution. Each 1-hour forecast $F_h$ covers two half-hour settlement periods.
- **UTC Arithmetic:** Association of hourly forecasts with half-hourly intervals is performed in **UTC** rather than local time. Because UTC is monotonic and invariant to daylight-saving clock changes, adding 30 minutes in UTC always advances time by exactly 30 physical minutes, preserving exact energy conservation ($E_h = F_h \times 0.5\text{ h} + F_h \times 0.5\text{ h} = F_h \times 1.0\text{ h}$) without timezone fold ambiguity.

### 3. Daylight Saving Time (DST) Handling

The platform handles UK daylight saving transitions (`Europe/London`):

| Transition | Month | Settlement Periods | Specific Behavior |
| :--- | :--- | :---: | :--- |
| **Autumn Fallback (BST $\to$ GMT)** | October 2025 | **1,490** | On Sunday 26 October 2025, clocks fall back from 02:00 BST to 01:00 GMT. The day has **25 hours = 50 settlement periods** ($30 \times 48 + 50 = 1,490$). The local wall-clock hour `01:00` to `02:00` repeats. Performing expansion in UTC preserves unique keys for SP 5 (`01:00 UTC`, GMT) and SP 6 (`01:30 UTC`, GMT) rather than folding back into BST SP 4 (`00:30 UTC`). |
| **Spring Forward (GMT $\to$ BST)** | March 2026 | **1,486** | On Sunday 29 March 2026, clocks advance from 01:00 GMT to 02:00 BST. The day has **23 hours = 46 settlement periods** ($30 \times 48 + 46 = 1,486$). The local wall-clock hour `01:00` to `02:00` is skipped. Monotonic UTC bounds accurately generate exactly 1,486 intervals. |
| **Standard Months** | Nov '25, Dec '25, Jan '26, Feb '26 | **1,440 / 1,488 / 1,344** | Standard 48-period days: 30 days = 1,440; 31 days = 1,488; 28 days (Feb 2026) = 1,344. |

### 4. Metric Definitions
For $N$ paired settlement periods where both $\hat{y}_i$ (forecast) and $y_i$ (actual) are available:
- **Mean Absolute Error (MAE):**
  $$\text{MAE} = \frac{1}{N} \sum_{i=1}^N |\hat{y}_i - y_i|$$
- **Root Mean Squared Error (RMSE):**
  $$\text{RMSE} = \sqrt{\frac{1}{N} \sum_{i=1}^N (\hat{y}_i - y_i)^2}$$
- **Forecast Bias:**
  $$\text{Bias} = \frac{1}{N} \sum_{i=1}^N (\hat{y}_i - y_i)$$
  *(Positive bias indicates a persistent tendency to over-forecast wind generation).*
- **Weighted Absolute Percentage Error (WAPE):**
  $$\text{WAPE} = \frac{\sum_{i=1}^N |\hat{y}_i - y_i|}{\sum_{i=1}^N y_i} \times 100$$

*(Periods where either the forecast or actual is missing are excluded from paired accuracy metrics).*

---

## Performance Optimization Results

| Metric | Original Implementation | Optimized Implementation | Improvement |
|---|---|---|---|
| Upstream HTTP Calls | 71 sequential calls | 2 bulk stream queries | **97.2% reduction** |
| Cold API Latency | 27.8 seconds | 2.44 seconds | **11.4x faster** |
| Cached API Latency | N/A (no caching) | 0.10 seconds | **278x faster** |
| Matched Coverage (Jan 2026) | 1,488 / 1,488 (100%) | 1,488 / 1,488 (100%) | 100% parity |
| Matched Coverage (Oct 2025) | 1,489 / 1,490 (99.9%) | 1,490 / 1,490 (100%) | 100% parity (DST bug resolved) |
| Matched Coverage (Mar 2026) | 1,486 / 1,486 (100%) | 1,486 / 1,486 (100%) | 100% parity |

---

## Known Limitations & Production Roadmap

1. **Illustrative Residual Demand:** System demand in the residual procurement panel is user-entered; real production requires actual National Grid ESO demand data (`INDO`/`ITSDO`).
2. **Single In-Memory Process Cache:** The current cache uses an in-memory TTL dictionary. Multi-replica cloud deployments should use a shared Redis cache.
3. **Public Deployment & Git Remote:** In accordance with instructions, Git initialization and public deployment are awaiting explicit user approval.

---

## AI-Assisted Development Disclosure

Portions of this codebase, test suites, architecture audit, and documentation were developed with assistance from Google Antigravity (Advanced Agentic AI). All API queries, numerical formulas, daylight-saving transitions, and visual behaviors were verified against live Elexon BMRS data.

---

## Final Submission Checklist

- [x] ComposedChart renders both forecast area and actual generation line.
- [x] Backend response latency $\le 3$ seconds with bulk queries and caching.
- [x] Dynamic delivery-month selector supporting October 2025 through March 2026.
- [x] Selectable decision cutoffs (08:00, 10:00, 12:00, and 16:00 UK time on $D-1$).
- [x] Settlement periods view provides full navigation across all monthly intervals (1,344 to 1,490).
- [x] Daylight-saving-time handling verified for both repeated-hour (October) and skipped-hour (March) clock changes.
- [x] Automated test suite (**24 tests**) passing cleanly via `pytest`.
- [x] Frontend dependencies pinned with committed `package-lock.json`.
- [x] Docker Compose health check configured and verified.
- [x] CSV export includes complete delivery, cutoff, and settlement metadata.
- [ ] Initialize Git repository (`git init`), create commit, and push to anonymous GitHub repository (Awaiting User Approval).
- [ ] Deploy to public cloud platform (Awaiting User Approval).
- [ ] Record 10-minute video walkthrough following `VIDEO_SCRIPT.md`.
