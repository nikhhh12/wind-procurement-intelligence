# Wind Procurement Intelligence

A full-stack operational analytics platform for a UK electricity utility's day-ahead power trading and procurement desk. The platform evaluates multi-month national wind generation forecasts from the Elexon BMRS Insights API (`WINDFOR`) against metered wind generation actuals (`FUELHH`) and quantifies forecast error at half-hourly settlement resolution.

> **Trading and operational disclaimer:** This platform is intended for analytical backtesting, decision intelligence, and strategy review—not automated trading or procurement execution. The selected decision cutoff defaults to 10:00 UK time on the calendar day before delivery (D-1), with configurable cutoffs at 08:00, 10:00, 12:00, and 16:00 UK time. The residual procurement panel uses an illustrative, user-entered demand assumption; system demand is not sourced from Elexon in this demonstration.

---

## Dashboard Preview

<!-- Add a real screenshot at docs/dashboard.png and uncomment the image below when available. -->

<!-- ![Wind Procurement Intelligence dashboard](docs/dashboard.png) -->

The dashboard provides monthly forecast-accuracy KPIs, a daily forecast-versus-actual chart, settlement-period inspection, and an illustrative residual procurement calculator.

## Key Features

- **Multi-month historical analysis:** Supports six delivery months, from October 2025 through March 2026, discoverable through `/api/supported-months`.
- **Selectable decision cutoffs:** Evaluates forecasts using 08:00, 10:00, 12:00, or 16:00 UK local time on D-1.
- **Forecast-accuracy KPIs:** Reports Mean Absolute Error (MAE), Root Mean Squared Error (RMSE), forecast bias, Weighted Absolute Percentage Error (WAPE), and matched-period coverage.
- **Daily generation visualization:** Uses Recharts `ComposedChart` to display forecast generation and actual metered outturn.
- **Settlement-period explorer:** Supports day-level navigation and a full-month view, with interval counts that account for month length and UK daylight-saving transitions.
- **Residual procurement calculator:** Estimates illustrative residual demand using a user-entered demand assumption and the selected date's mean forecast wind generation.
- **CSV export:** Exports settlement-level records, including timestamps, forecast and actual MW, error values, publication timestamps, and run metadata.
- **Bulk API ingestion:** Uses Elexon streaming endpoints for actuals and forecasts. The implementation history reports a reduction from 71 upstream requests to two bulk queries.
- **Anti-hindsight forecast selection:** Selects the latest eligible forecast vintage published no later than the configured D-1 cutoff.
- **Daylight-saving-time-safe alignment:** Uses UTC-based half-hourly interval expansion to prevent repeated-hour and skipped-hour alignment defects.
- **API caching:** Uses an in-memory time-to-live (TTL) cache to reduce repeated upstream requests.

## Architecture and Technology Stack

```text
┌──────────────────────────────────────────────────┐
│                 Browser / Client                 │
│           React · Vite · Recharts                │
└──────────────────────┬───────────────────────────┘
                       │ HTTP /api/
                       ▼
┌──────────────────────────────────────────────────┐
│              Nginx Reverse Proxy                 │
│          Static hosting · API routing            │
└──────────────────────┬───────────────────────────┘
                       │ Proxy to backend:8000
                       ▼
┌──────────────────────────────────────────────────┐
│                 FastAPI Backend                  │
│          Python · Requests · TTL Cache            │
│                                                  │
│  /api/health                                     │
│  /api/supported-months                           │
│  /api/analysis                                   │
└──────────────────────┬───────────────────────────┘
                       │ HTTPS
                       ▼
┌──────────────────────────────────────────────────┐
│              Elexon BMRS Insights API            │
│                                                  │
│  FUELHH/stream · Actual wind generation           │
│  WINDFOR/stream · Wind generation forecasts       │
└──────────────────────────────────────────────────┘
```

### Frontend

- React 18
- Vite
- Recharts
- Lucide React
- CSS design tokens and responsive layouts

### Backend

- Python 3.12
- FastAPI
- Uvicorn
- Requests
- Pytest and HTTPX

### Infrastructure

- Docker and Docker Compose
- Nginx Alpine
- Multi-stage container builds
- Nginx reverse proxy for API requests

## Repository Structure

```text
.
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   ├── requirements.txt
│   └── tests/
│       ├── __init__.py
│       └── test_analysis.py
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   └── src/
│       ├── main.jsx
│       └── style.css
├── docker-compose.yml
├── PROJECT_AUDIT_REPORT.md
├── IMPLEMENTATION_SUMMARY.md
├── VIDEO_SCRIPT.md
└── README.md
```

## Quick Start with Docker

### Prerequisites

- Docker Engine 24.0 or later, or Docker Desktop
- Docker Compose

### Run the application

Clone the repository and enter its directory:

```bash
git clone https://github.com/nikhhh12/wind-procurement-intelligence.git
cd wind-procurement-intelligence
```

Build and start the services:

```bash
docker compose up --build
```

Once the services are ready, open:

| Service | URL |
|---|---|
| Dashboard | http://localhost:8080 |
| API health | http://localhost:8000/api/health |
| Supported months | http://localhost:8000/api/supported-months |
| Interactive API documentation | http://localhost:8000/docs |

The backend health check helps verify service readiness before the frontend proxy sends requests to it.

To stop the application:

```bash
docker compose down
```

## Run Locally Without Docker

### 1. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

On Windows, activate the virtual environment using:

```powershell
.venv\Scripts\activate
```

### 2. Start the frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Ensure the frontend's Vite proxy or API base URL is configured to route requests to the backend at `http://localhost:8000`, according to the project's actual configuration.

## API Specification

### `GET /api/health`

Returns the backend health status.

Example response:

```json
{
  "status": "ok",
  "service": "wind-procurement-intelligence"
}
```

### `GET /api/supported-months`

Returns the supported delivery months and default selection.

Example response:

```json
{
  "supportedMonths": [
    "2025-10",
    "2025-11",
    "2025-12",
    "2026-01",
    "2026-02",
    "2026-03"
  ],
  "defaultMonth": "2026-01"
}
```

### `GET /api/analysis`

Fetches and computes forecast-accuracy metrics and settlement-period details for the selected delivery month and decision cutoff.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `month` | String | `2026-01` | Delivery month in `YYYY-MM` format; must be supported. |
| `cutoff_hour` | Integer | `10` | D-1 cutoff hour in the `Europe/London` timezone. The UI offers 8, 10, 12, and 16. |
| `refresh` | Boolean | `false` | If supported by the backend, bypasses cached data and requests fresh upstream data. |

Example request:

```text
GET /api/analysis?month=2026-01&cutoff_hour=10
```

The response provides the selected month and cutoff, data-source metadata, record counts, accuracy metrics, daily aggregates, settlement-period rows, and methodology information.

> **Note:** Response values depend on the selected month, cutoff, and upstream data. Consult the live API response rather than treating example metrics as current results.

## Methodology and Calculation Rules

### 1. Decision cutoff and forecast-vintage selection

For a delivery date \(D\), the configured decision cutoff is the selected hour on the previous UK calendar day:

\[
\operatorname{Cutoff}(D)
=
(D-1)\text{ day at cutoff\_hour in Europe/London}
\]

For a settlement interval \(t\), a forecast is eligible only when it covers that interval and was published by the cutoff:

\[
\mathcal{F}_{\mathrm{eligible}}(t,D)
=
\left\{
f \;\middle|\;
\operatorname{start}(f)\le t<\operatorname{end}(f),
\quad
\operatorname{publishTime}(f)\le\operatorname{Cutoff}(D)
\right\}
\]

The selected forecast is the eligible publication with the latest publication timestamp:

\[
\hat{y}(t)
=
\underset{f\in\mathcal{F}_{\mathrm{eligible}}(t,D)}
{\operatorname{arg\,max}}
\operatorname{publishTime}(f)
\]

This prevents the analysis from using forecast revisions published after the configured decision cutoff.

### 2. Forecast resolution and UTC arithmetic

- `FUELHH` actuals are represented at half-hourly settlement resolution.
- `WINDFOR` forecasts are treated at hourly resolution by this implementation.
- Each hourly forecast value is mapped to the two corresponding half-hourly intervals.
- Interval alignment is performed in UTC to preserve monotonic time progression across daylight-saving transitions.

For an hourly forecast value \(F_h\) in MW, the corresponding energy over one hour is:

\[
E_h=F_h\times1\text{ hour}
\]

Equivalently, the two half-hourly intervals contribute:

\[
E_h=(F_h\times0.5)+(F_h\times0.5)
\]

MW is a measure of power; multiplying by duration gives energy in MWh.

### 3. Daylight-saving-time handling

The analysis accounts for UK clock changes using the `Europe/London` timezone and UTC-based interval arithmetic.

| Period | Expected half-hourly intervals | Explanation |
|---|---:|---|
| October 2025 | 1,490 | Includes a 25-hour autumn clock-change day. |
| November 2025 | 1,440 | 30 days × 48 intervals. |
| December 2025 | 1,488 | 31 days × 48 intervals. |
| January 2026 | 1,488 | 31 days × 48 intervals. |
| February 2026 | 1,344 | 28 days × 48 intervals. |
| March 2026 | 1,486 | Includes a 23-hour spring clock-change day. |

During the autumn transition, the local hour between 01:00 and 02:00 occurs twice. During the spring transition, that local hour is skipped. UTC-based interval expansion avoids treating repeated local timestamps as the same physical interval.

### 4. Forecast-accuracy metrics

For \(N\) paired settlement periods with forecast \(\hat{y}_i\) and actual \(y_i\):

**Mean Absolute Error (MAE)**

\[
\operatorname{MAE}
=
\frac{1}{N}\sum_{i=1}^{N}|\hat{y}_i-y_i|
\]

**Root Mean Squared Error (RMSE)**

\[
\operatorname{RMSE}
=
\sqrt{\frac{1}{N}\sum_{i=1}^{N}(\hat{y}_i-y_i)^2}
\]

**Forecast bias**

\[
\operatorname{Bias}
=
\frac{1}{N}\sum_{i=1}^{N}(\hat{y}_i-y_i)
\]

A positive bias indicates that forecasts are higher than actual generation on average.

**Weighted Absolute Percentage Error (WAPE)**

\[
\operatorname{WAPE}
=
\frac{\sum_{i=1}^{N}|\hat{y}_i-y_i|}
{\sum_{i=1}^{N}y_i}
\times100\%
\]

Periods without both a forecast and an actual are excluded from paired accuracy metrics. Coverage counts and missing-period counts should be reviewed alongside accuracy metrics.

## Automated Test Suite

The backend test suite covers core analytical behavior, API validation, caching, and daylight-saving edge cases.

The reported suite contains 24 tests covering:

- Health endpoint behavior
- Cutoff inclusion and exclusion boundaries
- Latest eligible forecast-vintage selection
- Missing forecast and actual periods
- Duplicate actual records
- Month boundaries and D-1 cutoff continuity
- UK timezone conversion
- Hourly-to-half-hourly forecast expansion
- MAE, RMSE, bias, and WAPE calculations
- Daily energy calculation
- Upstream timeout and malformed-response handling
- Query-parameter validation
- Supported and unsupported delivery months
- February and December settlement-period grids
- Cache behavior
- Autumn clock fallback and repeated settlement intervals
- Cutoff differentiation between 12:00 and 16:00

Run tests inside Docker:

```bash
docker compose exec backend pytest -v
```

Or, from the repository root with the required Python dependencies installed:

```bash
pytest backend/tests -v
```

**Previously reported result:** `24 passed, 1 warning` in the Docker container. Rerun the suite after code changes to confirm the current result.

## Performance Optimization

The implementation history reported the following improvements. Latency figures are environment-specific measurements, not guaranteed production service-level objectives.

| Metric | Reported original | Reported optimized |
|---|---:|---:|
| Upstream HTTP requests | 71 sequential calls | 2 bulk queries |
| Cold API latency | 27.8 seconds | 2.44 seconds |
| Cached API latency | No caching | 0.10 seconds |

For reproducible benchmarking, record the environment, selected month and cutoff, cache state, number of runs, and measurement method.

## Known Limitations and Future Improvements

1. **Illustrative residual demand:** The residual procurement calculator uses user-entered demand. A production implementation should integrate an authoritative demand data source.
2. **In-memory cache:** The TTL cache is process-local. A multi-replica deployment would benefit from a shared cache such as Redis.
3. **Historical data availability:** The current supported analysis window is October 2025 through March 2026. Additional months require extending the supported data window and validating upstream coverage.
4. **Public deployment:** The local Docker setup does not itself create a publicly accessible service.
5. **Operational readiness:** The platform is an analytics demonstration and is not represented as a production trading system.

## AI-Assisted Development Disclosure

Parts of the codebase, test suite, architecture audit, and documentation were developed with assistance from Google Antigravity. Analytical behavior and numerical results should be verified against source data and reproducible tests before operational use.

## Project Status

Wind Procurement Intelligence includes a React analytics dashboard, FastAPI backend, Docker Compose setup, multi-month wind forecast analysis, and automated backend tests.

Public deployment, a dashboard screenshot, and a recorded walkthrough are optional enhancements that can further improve the project presentation.

---

**Repository:** [github.com/nikhhh12/wind-procurement-intelligence](https://github.com/nikhhh12/wind-procurement-intelligence)

**Local dashboard:** `http://localhost:8080` after starting the Docker Compose stack.
