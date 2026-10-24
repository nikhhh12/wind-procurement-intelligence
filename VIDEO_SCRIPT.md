# 10-minute demo run-of-show

Use the actual deployed application while recording. Do not narrate sample or fabricated metrics if the API is unavailable.

## Part 1 — Client pitch (target 4:30)

**0:00–0:35 | Problem and outcome**
“Wind generation is uncertain, and day-ahead purchasing decisions must be made before delivery. This pilot makes the forecast vintage and its historical accuracy visible in one place, so the team can reason about residual procurement with a quantified view of uncertainty.”

**0:35–1:35 | KPI cards**
Explain MAE as typical absolute miss, RMSE as a metric more sensitive to large errors, and bias as the direction of systematic error. Call out matched periods and missing forecast coverage. Do not claim an accuracy level unless the live values support it.

**1:35–2:35 | Daily chart**
Show forecast versus actual daily energy. Describe deviations as periods to investigate, not as proof that a specific trade would have been profitable. Explain that the data is national aggregated wind generation from Elexon.

**2:35–3:30 | Settlement period and forecast vintage**
Select a delivery date and inspect half-hour values and the publication timestamp. Explain that the selected record must have been published by the configured cutoff on the prior UK day, preventing hindsight leakage.

**3:30–4:30 | Procurement illustration and close**
Enter a demand assumption. Explain that residual = assumed demand minus mean wind forecast, floored at zero. Clearly state this is illustrative and excludes other generation, imports, storage, losses, and market prices. Close with value: a traceable forecast, measurable error, and an auditable starting point for a production workflow.

## Part 2 — Technical lead review (target 4:45)

**4:30–5:15 | Architecture**
React/Vite UI calls FastAPI. FastAPI retrieves FUELHH and WINDFOR from Elexon's public Insights API. Docker Compose runs the Python service and Nginx-hosted SPA; Nginx proxies `/api/` to FastAPI.

**5:15–6:30 | Data and selection logic**
Walk through `backend/main.py`: bounded January date window; FUELHH filter `fuelType == WIND`; parse timestamps with explicit timezone handling; for each target interval calculate the prior UK calendar day's cutoff; select the maximum eligible `publishTime`; then pair with actuals by UTC `startTime`.

**6:30–7:30 | Analytics**
Show paired-period-only MAE, RMSE, bias and WAPE. Explain why forecast vintage selection matters and why missing forecasts should not be silently filled or evaluated using later revisions. Daily energy is half-hourly MW multiplied by 0.5 hours.

**7:30–8:30 | Frontend and API contract**
Show `frontend/src/main.jsx`: KPI cards, chart, settlement table, CSV export and assumption-based residual calculator. API response includes rows, publication times, counts, metrics, and methodology.

**8:30–9:15 | Delivery and operational considerations**
Show Dockerfiles and `docker-compose.yml`. Explain no hardcoded credentials, public Elexon API, timeout/error surfacing, and the need for caching, retry/backoff, tests, duplicate handling, and monitoring before production.

**9:15–9:30 | Close**
Summarize the key trade-off: a small, reviewable pilot that prioritizes forecast-vintage correctness and transparent metrics over pretending to be a full trading system.
