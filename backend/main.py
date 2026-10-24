from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import calendar
import os
import time as time_module
from typing import Any
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="Wind Procurement Intelligence API",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = os.getenv(
    "ELEXON_API_BASE",
    "https://data.elexon.co.uk/bmrs/api/v1",
).rstrip("/")

LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc
HALF_HOUR = timedelta(minutes=30)

CACHE_TTL_SECONDS = int(os.getenv("ELEXON_CACHE_TTL_SECONDS", "3600"))
_RAW_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}

SUPPORTED_MONTHS = [
    "2025-10",
    "2025-11",
    "2025-12",
    "2026-01",
    "2026-02",
    "2026-03",
]
DEFAULT_MONTH = "2026-01"


def get_month_bounds(month: str) -> tuple[datetime, datetime, int, int, int]:
    """
    Parse a YYYY-MM month string and return:
    (local_start, local_end, year, month_num, last_day)
    where local_start and local_end are in Europe/London timezone.
    """
    try:
        parts = month.split("-")
        year = int(parts[0])
        month_num = int(parts[1])
        if not (1 <= month_num <= 12):
            raise ValueError()
    except (ValueError, IndexError):
        raise ValueError(f"Invalid month format: {month}. Expected YYYY-MM.")

    last_day = calendar.monthrange(year, month_num)[1]
    local_start = datetime(year, month_num, 1, 0, 0, 0, tzinfo=LONDON)
    if month_num == 12:
        local_end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=LONDON)
    else:
        local_end = datetime(year, month_num + 1, 1, 0, 0, 0, tzinfo=LONDON)

    return local_start, local_end, year, month_num, last_day


def in_month(dt: datetime, year: int, month_num: int) -> bool:
    """Return whether dt (when converted to Europe/London) falls within year and month_num."""
    local = dt.astimezone(LONDON)
    return local.year == year and local.month == month_num


def in_january(dt: datetime) -> bool:
    """Preserved for backwards compatibility with tests."""
    return in_month(dt, 2026, 1)


def parse_dt(value: Any) -> datetime | None:
    """Parse an ISO timestamp and normalize naive timestamps to UTC."""
    if not value:
        return None

    try:
        result = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if result.tzinfo is None:
            result = result.replace(tzinfo=UTC)
        return result
    except (ValueError, TypeError):
        return None


def num(value: Any) -> float | None:
    """Convert a numeric API value, ignoring missing values."""
    try:
        if value is None or str(value).strip().upper() in {
            "",
            "NULL",
            "N/A",
        }:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def utc_key(dt: datetime) -> str:
    """Produce a consistent UTC key for timestamps."""
    return dt.astimezone(UTC).isoformat()


def cutoff_for_delivery(
    delivery_start: datetime,
    cutoff_hour: int,
) -> datetime:
    """
    Return the UTC instant corresponding to the configured cutoff
    on the previous UK calendar day.
    """
    local_delivery = delivery_start.astimezone(LONDON)
    decision_day = local_delivery.date() - timedelta(days=1)

    local_cutoff = datetime.combine(
        decision_day,
        time(cutoff_hour, 0),
        tzinfo=LONDON,
    )
    return local_cutoff.astimezone(UTC)


def forecast_period_keys(
    forecast_start: datetime,
) -> list[str]:
    """
    WINDFOR records are hourly in the returned sample, whereas FUELHH
    actuals are half-hourly. Associate an hourly forecast with the
    two half-hour delivery intervals within that hour.

    A forecast timestamp on the half-hour is retained as that interval.

    Arithmetic is performed in UTC to preserve continuous 30-minute steps
    and avoid fold/daylight-saving ambiguities during clock change transitions
    (such as the autumn clock-fallback where local wall-clock times repeat).
    """
    utc_start = forecast_start.astimezone(UTC)

    if utc_start.minute == 30:
        return [utc_key(utc_start)]

    hour_start = utc_start.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    return [
        utc_key(hour_start),
        utc_key(hour_start + HALF_HOUR),
    ]


def _fallback_fetch_stream(
    dataset: str,
    start: datetime,
    end: datetime,
    session: requests.Session,
    chunk_days: int = 1,
) -> list[dict[str, Any]]:
    """Fallback chunked fetching for resilience against large payload timeouts."""
    url = f"{BASE}/datasets/{dataset}/stream"
    results: list[dict[str, Any]] = []
    cursor = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)

    while cursor < end_utc:
        next_chunk = datetime.combine(
            cursor.date() + timedelta(days=chunk_days),
            time.min,
            tzinfo=UTC,
        )
        chunk_end = min(next_chunk, end_utc)

        response = session.get(
            url,
            params={
                "publishDateTimeFrom": cursor.isoformat(),
                "publishDateTimeTo": chunk_end.isoformat(),
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            payload = payload.get("data", [])

        if not isinstance(payload, list):
            raise ValueError(f"Unexpected {dataset} response format")

        results.extend(row for row in payload if isinstance(row, dict))
        cursor = chunk_end

    return results


def fetch_fuelhh_actuals(
    month: str = "2026-01",
    refresh: bool = False,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch FUELHH actual wind generation records.
    Uses Elexon's native settlementDateFrom/settlementDateTo and fuelType=WIND
    parameters for bulk single-request retrieval with in-memory caching.
    """
    local_start, local_end, year, month_num, last_day = get_month_bounds(month)
    cache_key = f"FUELHH_{month}"
    now = time_module.time()

    if not refresh and cache_key in _RAW_CACHE:
        cached_time, cached_data = _RAW_CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    url = f"{BASE}/datasets/FUELHH/stream"
    params = {
        "settlementDateFrom": f"{month}-01",
        "settlementDateTo": f"{month}-{last_day:02d}",
        "fuelType": "WIND",
    }
    s = session or requests.Session()
    try:
        response = s.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            payload = payload.get("data", [])
        if not isinstance(payload, list):
            raise ValueError("Unexpected FUELHH response format")

        if not payload:
            # Fallback to chunked publishDateTime if settlementDate returns empty
            start_utc = local_start.astimezone(UTC)
            end_utc = local_end.astimezone(UTC) + timedelta(days=2)
            payload = _fallback_fetch_stream("FUELHH", start_utc, end_utc, s, chunk_days=2)

        _RAW_CACHE[cache_key] = (now, payload)
        return payload
    except (requests.RequestException, ValueError) as exc:
        if cache_key in _RAW_CACHE:
            return _RAW_CACHE[cache_key][1]
        raise HTTPException(
            status_code=502,
            detail=f"Elexon FUELHH request failed: {exc}",
        ) from exc


def fetch_windfor_forecasts(
    month: str = "2026-01",
    refresh: bool = False,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch WINDFOR forecast records.
    Uses bulk publishDateTimeFrom/To streaming with in-memory caching.
    """
    local_start, local_end, _, _, _ = get_month_bounds(month)
    cache_key = f"WINDFOR_{month}"
    now = time_module.time()

    if not refresh and cache_key in _RAW_CACHE:
        cached_time, cached_data = _RAW_CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_data

    url = f"{BASE}/datasets/WINDFOR/stream"
    start_utc = local_start.astimezone(UTC) - timedelta(days=7)
    end_utc = local_end.astimezone(UTC)
    params = {
        "publishDateTimeFrom": start_utc.isoformat(),
        "publishDateTimeTo": end_utc.isoformat(),
    }
    s = session or requests.Session()
    try:
        response = s.get(url, params=params, timeout=45)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            payload = payload.get("data", [])
        if not isinstance(payload, list):
            raise ValueError("Unexpected WINDFOR response format")

        _RAW_CACHE[cache_key] = (now, payload)
        return payload
    except (requests.RequestException, ValueError) as exc:
        # Fallback to 7-day chunks if single bulk call times out
        try:
            chunked_results = _fallback_fetch_stream(
                "WINDFOR", start_utc, end_utc, s, chunk_days=7
            )
            _RAW_CACHE[cache_key] = (now, chunked_results)
            return chunked_results
        except Exception:
            if cache_key in _RAW_CACHE:
                return _RAW_CACHE[cache_key][1]
            raise HTTPException(
                status_code=502,
                detail=f"Elexon WINDFOR request failed: {exc}",
            ) from exc


def calculate_analysis(
    actuals_raw: list[dict[str, Any]],
    forecasts_raw: list[dict[str, Any]],
    cutoff_hour: int = 10,
    month: str = "2026-01",
) -> dict[str, Any]:
    """
    Evaluate forecasts against actuals for the specified month.
    Separated from network fetching to allow pure, fast, deterministic testing.
    """
    local_start, local_end, year, month_num, _ = get_month_bounds(month)

    target_start = local_start.astimezone(UTC)
    target_end = local_end.astimezone(UTC)

    # Deduplicate actuals by delivery period, retaining the latest published record
    # tuple: (published, generation, settlementPeriod, settlementDate)
    actual_candidates: dict[str, tuple[datetime, float, Any, Any]] = {}

    for row in actuals_raw:
        if str(row.get("fuelType", "")).upper() != "WIND":
            continue

        delivery = parse_dt(row.get("startTime"))
        published = parse_dt(row.get("publishTime"))
        generation = num(row.get("generation"))
        sp = row.get("settlementPeriod")
        sdate = row.get("settlementDate")

        if (
            delivery is None
            or published is None
            or generation is None
            or not in_month(delivery, year, month_num)
        ):
            continue

        key = utc_key(delivery)
        previous = actual_candidates.get(key)

        if previous is None or published > previous[0]:
            actual_candidates[key] = (published, generation, sp, sdate)

    actuals = {
        key: item[1]
        for key, item in actual_candidates.items()
    }

    # Keep eligible forecast vintages for each half-hourly delivery period.
    forecast_candidates: dict[str, list[tuple[datetime, float]]] = {}

    for row in forecasts_raw:
        delivery = parse_dt(row.get("startTime"))
        published = parse_dt(row.get("publishTime"))
        generation = num(row.get("generation"))

        if (
            delivery is None
            or published is None
            or generation is None
            or not in_month(delivery, year, month_num)
        ):
            continue

        # Do not use forecasts published after the decision cutoff.
        cutoff = cutoff_for_delivery(delivery, cutoff_hour)
        if published.astimezone(UTC) > cutoff:
            continue

        for key in forecast_period_keys(delivery):
            period_start = datetime.fromisoformat(key)

            if not in_month(period_start, year, month_num):
                continue

            forecast_candidates.setdefault(key, []).append(
                (published.astimezone(UTC), generation)
            )

    # Build a full half-hourly month grid.
    rows = []
    period_start = target_start

    while period_start < target_end:
        key = utc_key(period_start)
        options = forecast_candidates.get(key, [])

        # Choose the latest eligible publication for this delivery period.
        chosen = max(options, key=lambda item: item[0]) if options else None

        actual_info = actual_candidates.get(key)
        actual = actual_info[1] if actual_info is not None else None
        forecast = chosen[1] if chosen is not None else None
        local_time = period_start.astimezone(LONDON)

        default_sp = (
            local_time.hour * 2
            + (1 if local_time.minute >= 30 else 0)
            + 1
        )
        settlement_period = (
            actual_info[2]
            if (actual_info is not None and actual_info[2] is not None)
            else default_sp
        )
        settlement_date = (
            actual_info[3]
            if (actual_info is not None and actual_info[3])
            else local_time.date().isoformat()
        )

        error = (
            forecast - actual
            if forecast is not None and actual is not None
            else None
        )

        rows.append(
            {
                "startTime": key,
                "localTime": local_time.isoformat(),
                "settlementDate": settlement_date,
                "settlementPeriod": settlement_period,
                "actualMW": actual,
                "forecastMW": forecast,
                "publishTime": (
                    chosen[0].isoformat()
                    if chosen is not None
                    else None
                ),
                "errorMW": error,
                "absoluteErrorMW": (
                    abs(error) if error is not None else None
                ),
            }
        )

        period_start += HALF_HOUR

    paired = [
        row
        for row in rows
        if row["actualMW"] is not None
        and row["forecastMW"] is not None
    ]

    if paired:
        errors = [row["errorMW"] for row in paired]
        absolute_errors = [row["absoluteErrorMW"] for row in paired]

        mae = sum(absolute_errors) / len(paired)
        bias = sum(errors) / len(paired)
        rmse = (sum(error**2 for error in errors) / len(paired)) ** 0.5

        actual_sum = sum(row["actualMW"] for row in paired)
        wape = (
            sum(absolute_errors) / actual_sum * 100
            if actual_sum > 0
            else None
        )
    else:
        mae = bias = rmse = wape = None

    daily: dict[str, dict[str, Any]] = {}

    for row in paired:
        day = row["settlementDate"]

        bucket = daily.setdefault(
            day,
            {
                "date": day,
                "actualTotal": 0.0,
                "forecastTotal": 0.0,
                "periods": 0,
                "absErrorTotal": 0.0,
            },
        )

        # Convert half-hourly MW averages to MWh.
        bucket["actualTotal"] += row["actualMW"] * 0.5
        bucket["forecastTotal"] += row["forecastMW"] * 0.5
        bucket["absErrorTotal"] += row["absoluteErrorMW"] * 0.5
        bucket["periods"] += 1

    missing_forecasts = sum(
        1
        for row in rows
        if row["actualMW"] is not None
        and row["forecastMW"] is None
    )

    month_name = local_start.strftime("%B %Y")
    return {
        "month": month,
        "cutoffHourLondon": cutoff_hour,
        "source": "Elexon BMRS Insights API",
        "generatedAt": datetime.now(UTC).isoformat(),
        "counts": {
            "actualRecords": len(actuals),
            "forecastRecords": sum(
                len(candidates)
                for candidates in forecast_candidates.values()
            ),
            "pairedPeriods": len(paired),
            "missingForecastPeriods": missing_forecasts,
            "expectedPeriods": len(rows),
        },
        "metrics": {
            "maeMW": mae,
            "rmseMW": rmse,
            "biasMW": bias,
            "wapePercent": wape,
        },
        "daily": list(daily.values()),
        "rows": rows,
        "methodology": (
            f"{month_name} delivery periods are evaluated in UK local time. "
            "For each half-hourly delivery period, the latest WINDFOR "
            "publication available by the configured cutoff on the "
            "previous UK calendar day is selected. Hourly forecast records "
            "are associated with both half-hour periods in their hour. "
            "Actuals are deduplicated by delivery period using the latest "
            "publication returned by Elexon. Accuracy metrics use only "
            "periods with both actual and forecast values. Historical "
            "coverage depends on the records returned by the source API."
        ),
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "wind-procurement-intelligence",
    }


@app.get("/api/supported-months")
def supported_months():
    """Return the list of delivery months supported by this service."""
    return {
        "supportedMonths": SUPPORTED_MONTHS,
        "defaultMonth": DEFAULT_MONTH,
    }


@app.get("/api/analysis")
def analysis(
    month: str = Query("2026-01", pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    cutoff_hour: int = Query(10, ge=0, le=23),
    refresh: bool = Query(False, description="Force re-fetch from Elexon bypassing cache"),
):
    if month not in SUPPORTED_MONTHS:
        raise HTTPException(
            status_code=400,
            detail=f"Month '{month}' is not currently supported. Supported months: {', '.join(SUPPORTED_MONTHS)}",
        )
    actuals_raw = fetch_fuelhh_actuals(month=month, refresh=refresh)
    forecasts_raw = fetch_windfor_forecasts(month=month, refresh=refresh)
    return calculate_analysis(
        actuals_raw=actuals_raw,
        forecasts_raw=forecasts_raw,
        cutoff_hour=cutoff_hour,
        month=month,
    )