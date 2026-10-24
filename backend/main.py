from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any
import os
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from functools import lru_cache

app = FastAPI(title="Wind Procurement Intelligence API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
BASE = os.getenv("ELEXON_API_BASE", "https://data.elexon.co.uk/bmrs/api/v1")
LONDON = ZoneInfo("Europe/London")



def fetch_stream(dataset: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    url = f"{BASE}/datasets/{dataset}/stream"

    try:
        response = requests.get(
            url,
            params={
                "publishDateTimeFrom": start.astimezone(timezone.utc).isoformat(),
                "publishDateTimeTo": end.astimezone(timezone.utc).isoformat(),
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            payload = payload.get("data", [])

        if not isinstance(payload, list):
            raise ValueError("Unexpected Elexon response shape")

        return payload

    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Elexon {dataset} request failed: {exc}",
        ) from exc



def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def num(value: Any) -> float | None:
    try:
        return float(value) if value is not None and str(value).strip().upper() not in {"", "NULL", "N/A"} else None
    except (TypeError, ValueError):
        return None


def in_january(dt: datetime) -> bool:
    local = dt.astimezone(LONDON)
    return local.year == 2026 and local.month == 1

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "wind-procurement-intelligence"}

@app.get("/api/analysis")
def analysis(
    month: str = Query("2026-01", pattern=r"^2026-01$"),
    cutoff_hour: int = Query(10, ge=0, le=23),
):
    # The selected month is deliberately constrained to the assignment's January 2026 scope.
    target_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    target_end = datetime(2026, 2, 1, tzinfo=timezone.utc)
    # Include the prior day so forecasts published on the decision day can be retrieved.
    forecast_start = target_start - timedelta(days=2)
    forecast_end = target_end
    actuals_raw = fetch_stream("FUELHH", target_start, target_end)
    forecasts_raw = fetch_stream("WINDFOR", forecast_start, forecast_end)

    actuals: dict[str, float] = {}
    for row in actuals_raw:
        if str(row.get("fuelType", "")).upper() != "WIND":
            continue
        start = parse_dt(row.get("startTime"))
        generation = num(row.get("generation"))
        if start and generation is not None and in_january(start):
            actuals[start.astimezone(timezone.utc).isoformat()] = generation

    # Keep forecast vintages; for each target half-hour choose the newest publication
    # available by the configured cutoff on the preceding UK calendar day.
    forecast_candidates: dict[str, list[tuple[datetime, float]]] = {}
    for row in forecasts_raw:
        target = parse_dt(row.get("startTime"))
        published = parse_dt(row.get("publishTime"))
        generation = num(row.get("generation"))
        if not target or not published or generation is None or not in_january(target):
            continue
        local_target = target.astimezone(LONDON)
        decision_day = local_target.date() - timedelta(days=1)
        cutoff = datetime.combine(decision_day, time(cutoff_hour, 0), tzinfo=LONDON).astimezone(timezone.utc)
        if published <= cutoff:
            key = target.astimezone(timezone.utc).isoformat()
            forecast_candidates.setdefault(key, []).append((published, generation))

    rows = []
    for key in sorted(set(actuals) | set(forecast_candidates)):
        options = forecast_candidates.get(key, [])
        chosen = max(options, key=lambda x: x[0]) if options else None
        actual = actuals.get(key)
        forecast = chosen[1] if chosen else None
        target_dt = datetime.fromisoformat(key).astimezone(LONDON)
        error = forecast - actual if forecast is not None and actual is not None else None
        rows.append({
            "startTime": key,
            "localTime": target_dt.isoformat(),
            "settlementDate": target_dt.date().isoformat(),
            "settlementPeriod": int(target_dt.hour * 2 + (1 if target_dt.minute >= 30 else 0) + 1),
            "actualMW": actual,
            "forecastMW": forecast,
            "publishTime": chosen[0].isoformat() if chosen else None,
            "errorMW": error,
            "absoluteErrorMW": abs(error) if error is not None else None,
        })
    paired = [r for r in rows if r["actualMW"] is not None and r["forecastMW"] is not None]
    if paired:
        mae = sum(r["absoluteErrorMW"] for r in paired) / len(paired)
        bias = sum(r["errorMW"] for r in paired) / len(paired)
        actual_sum = sum(r["actualMW"] for r in paired)
        wape = sum(r["absoluteErrorMW"] for r in paired) / actual_sum * 100 if actual_sum else None
        rmse = (sum(r["errorMW"] ** 2 for r in paired) / len(paired)) ** 0.5
    else:
        mae = bias = wape = rmse = None
    daily = {}
    for r in paired:
        d = r["settlementDate"]
        bucket = daily.setdefault(d, {"date": d, "actualTotal": 0.0, "forecastTotal": 0.0, "periods": 0, "absErrorTotal": 0.0})
        bucket["actualTotal"] += r["actualMW"] * 0.5
        bucket["forecastTotal"] += r["forecastMW"] * 0.5
        bucket["absErrorTotal"] += r["absoluteErrorMW"]
        bucket["periods"] += 1
    return {
        "month": month,
        "cutoffHourLondon": cutoff_hour,
        "source": "Elexon BMRS Insights API",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "counts": {"actualRecords": len(actuals), "forecastRecords": sum(len(v) for v in forecast_candidates.values()), "pairedPeriods": len(paired), "missingForecastPeriods": sum(1 for r in rows if r["actualMW"] is not None and r["forecastMW"] is None)},
        "metrics": {"maeMW": mae, "rmseMW": rmse, "biasMW": bias, "wapePercent": wape},
        "daily": list(daily.values()),
        "rows": rows,
        "methodology": "For each January delivery half-hour, select the latest WINDFOR publication timestamp no later than the configured cutoff (UK local time) on the preceding calendar day. Compare it with FUELHH WIND actual generation. Only periods with both values contribute to accuracy metrics."
    }