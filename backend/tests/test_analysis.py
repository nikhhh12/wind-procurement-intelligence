from __future__ import annotations

from datetime import datetime, timezone
import requests
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import (
    app,
    calculate_analysis,
    cutoff_for_delivery,
    fetch_fuelhh_actuals,
    fetch_windfor_forecasts,
    forecast_period_keys,
    LONDON,
    UTC,
    _RAW_CACHE,
)

client = TestClient(app)


def test_health_check():
    """Verify health endpoint responds with ok status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "wind-procurement-intelligence",
    }


def test_cutoff_inclusion_boundary():
    """A forecast published at exactly the cutoff instant (e.g. 10:00:00 on D-1) is eligible."""
    delivery = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    cutoff = cutoff_for_delivery(delivery, cutoff_hour=10)
    assert cutoff == datetime(2026, 1, 14, 10, 0, tzinfo=UTC)

    # Forecast published at exactly 10:00:00
    at_cutoff = datetime(2026, 1, 14, 10, 0, 0, tzinfo=UTC)
    assert at_cutoff <= cutoff

    forecasts = [
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T10:00:00Z",
            "generation": 5000,
        }
    ]
    actuals = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-15T12:30:00Z",
            "generation": 4500,
        }
    ]
    result = calculate_analysis(actuals, forecasts, cutoff_hour=10)
    row = next(r for r in result["rows"] if r["startTime"] == "2026-01-15T12:00:00+00:00")
    assert row["forecastMW"] == 5000
    assert row["actualMW"] == 4500
    assert row["errorMW"] == 500


def test_cutoff_exclusion_boundary():
    """A forecast published at 10:00:01 (1 second after cutoff) must be excluded."""
    delivery = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    cutoff = cutoff_for_delivery(delivery, cutoff_hour=10)

    after_cutoff = datetime(2026, 1, 14, 10, 0, 1, tzinfo=UTC)
    assert after_cutoff > cutoff

    forecasts = [
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T10:00:01Z",
            "generation": 5000,
        }
    ]
    actuals = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-15T12:30:00Z",
            "generation": 4500,
        }
    ]
    result = calculate_analysis(actuals, forecasts, cutoff_hour=10)
    row = next(r for r in result["rows"] if r["startTime"] == "2026-01-15T12:00:00+00:00")
    assert row["forecastMW"] is None
    assert row["actualMW"] == 4500
    assert row["errorMW"] is None


def test_latest_eligible_vintage_selection():
    """When multiple vintages exist before the cutoff, the latest eligible vintage is selected."""
    forecasts = [
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T04:30:00Z",
            "generation": 4000,
        },
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T09:30:00Z",
            "generation": 5500,
        },
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T07:30:00Z",
            "generation": 4800,
        },
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T11:30:00Z",  # Ineligible: after 10:00 cutoff
            "generation": 7000,
        },
    ]
    actuals = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-15T13:00:00Z",
            "generation": 5000,
        }
    ]
    result = calculate_analysis(actuals, forecasts, cutoff_hour=10)
    row = next(r for r in result["rows"] if r["startTime"] == "2026-01-15T12:00:00+00:00")
    assert row["forecastMW"] == 5500
    assert row["publishTime"] == "2026-01-14T09:30:00+00:00"
    assert row["errorMW"] == 500


def test_missing_forecast_period():
    """Missing forecasts result in None for forecast and error, and increment missingForecastPeriods."""
    actuals = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-10T08:00:00Z",
            "publishTime": "2026-01-10T09:00:00Z",
            "generation": 6000,
        }
    ]
    # No forecasts provided
    result = calculate_analysis(actuals, [], cutoff_hour=10)
    row = next(r for r in result["rows"] if r["startTime"] == "2026-01-10T08:00:00+00:00")
    assert row["actualMW"] == 6000
    assert row["forecastMW"] is None
    assert row["errorMW"] is None
    assert result["counts"]["missingForecastPeriods"] == 1
    assert result["counts"]["pairedPeriods"] == 0


def test_missing_actual_period():
    """When actual is missing, it is excluded from paired accuracy calculations."""
    forecasts = [
        {
            "startTime": "2026-01-10T08:00:00Z",
            "publishTime": "2026-01-09T09:30:00Z",
            "generation": 7000,
        }
    ]
    # No actuals provided
    result = calculate_analysis([], forecasts, cutoff_hour=10)
    row = next(r for r in result["rows"] if r["startTime"] == "2026-01-10T08:00:00+00:00")
    assert row["forecastMW"] == 7000
    assert row["actualMW"] is None
    assert row["errorMW"] is None
    assert result["counts"]["pairedPeriods"] == 0
    assert result["metrics"]["maeMW"] is None


def test_duplicate_actual_publications():
    """Deduplication of actuals retains the latest published record."""
    actuals = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-05T14:00:00Z",
            "publishTime": "2026-01-05T14:30:00Z",
            "generation": 8000,
        },
        {
            "fuelType": "WIND",
            "startTime": "2026-01-05T14:00:00Z",
            "publishTime": "2026-01-05T16:00:00Z",  # Revision published later
            "generation": 8250,
        },
    ]
    result = calculate_analysis(actuals, [], cutoff_hour=10)
    row = next(r for r in result["rows"] if r["startTime"] == "2026-01-05T14:00:00+00:00")
    assert row["actualMW"] == 8250


def test_month_boundary_handling():
    """Verify 1 Jan uses 31 Dec cutoff, 31 Jan uses 30 Jan cutoff, and grid bounds are strictly 1-31 Jan."""
    start_jan = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    cutoff_jan1 = cutoff_for_delivery(start_jan, cutoff_hour=10)
    assert cutoff_jan1 == datetime(2025, 12, 31, 10, 0, tzinfo=UTC)

    end_jan = datetime(2026, 1, 31, 23, 30, tzinfo=UTC)
    cutoff_jan31 = cutoff_for_delivery(end_jan, cutoff_hour=10)
    assert cutoff_jan31 == datetime(2026, 1, 30, 10, 0, tzinfo=UTC)

    result = calculate_analysis([], [], cutoff_hour=10)
    assert len(result["rows"]) == 1488
    assert result["rows"][0]["startTime"] == "2026-01-01T00:00:00+00:00"
    assert result["rows"][-1]["startTime"] == "2026-01-31T23:30:00+00:00"


def test_timezone_conversion():
    """London cutoff hour is converted to UTC correctly."""
    delivery = datetime(2026, 1, 20, 15, 0, tzinfo=LONDON)
    cutoff_utc = cutoff_for_delivery(delivery, cutoff_hour=8)
    assert cutoff_utc == datetime(2026, 1, 19, 8, 0, tzinfo=timezone.utc)


def test_hourly_to_half_hourly_expansion():
    """Hourly forecast expands to both 30-minute intervals within the hour."""
    hourly_time = datetime(2026, 1, 10, 14, 0, tzinfo=UTC)
    keys = forecast_period_keys(hourly_time)
    assert len(keys) == 2
    assert keys[0] == "2026-01-10T14:00:00+00:00"
    assert keys[1] == "2026-01-10T14:30:00+00:00"


def test_accuracy_metric_formulas():
    """Verify MAE, RMSE, Bias, and WAPE match mathematical definitions with hourly forecast expansion."""
    # 2 hourly forecasts:
    # 00:00 -> 1800 MW (covers 00:00 and 00:30)
    # 01:00 -> 2200 MW (covers 01:00 and 01:30)
    # 4 half-hourly actuals:
    # SP 1 (00:00): act=1600, fc=1800 -> err=+200, |err|=200, err^2=40000
    # SP 2 (00:30): act=2000, fc=1800 -> err=-200, |err|=200, err^2=40000
    # SP 3 (01:00): act=1800, fc=2200 -> err=+400, |err|=400, err^2=160000
    # SP 4 (01:30): act=2200, fc=2200 -> err=0,    |err|=0,   err^2=0
    # Sum act = 7600
    # Bias = (+200 - 200 + 400 + 0) / 4 = +100.0 MW
    # MAE = (200 + 200 + 400 + 0) / 4 = 200.0 MW
    # RMSE = sqrt(240000 / 4) = sqrt(60000) = 244.95 MW
    # WAPE = (800 / 7600) * 100 = 10.53%
    actuals = [
        {"fuelType": "WIND", "startTime": "2026-01-01T00:00:00Z", "publishTime": "2026-01-01T02:00:00Z", "generation": 1600},
        {"fuelType": "WIND", "startTime": "2026-01-01T00:30:00Z", "publishTime": "2026-01-01T02:00:00Z", "generation": 2000},
        {"fuelType": "WIND", "startTime": "2026-01-01T01:00:00Z", "publishTime": "2026-01-01T02:00:00Z", "generation": 1800},
        {"fuelType": "WIND", "startTime": "2026-01-01T01:30:00Z", "publishTime": "2026-01-01T02:00:00Z", "generation": 2200},
    ]
    forecasts = [
        {"startTime": "2026-01-01T00:00:00Z", "publishTime": "2025-12-31T09:30:00Z", "generation": 1800},
        {"startTime": "2026-01-01T01:00:00Z", "publishTime": "2025-12-31T09:30:00Z", "generation": 2200},
    ]

    result = calculate_analysis(actuals, forecasts, cutoff_hour=10)
    metrics = result["metrics"]
    assert pytest.approx(metrics["maeMW"], 0.01) == 200.0
    assert pytest.approx(metrics["biasMW"], 0.01) == 100.0
    assert pytest.approx(metrics["rmseMW"], 0.01) == 244.95
    assert pytest.approx(metrics["wapePercent"], 0.01) == 10.53


def test_daily_energy_calculation():
    """Daily total MWh is sum of MW * 0.5."""
    actuals = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2026-01-01T01:00:00Z",
            "generation": 10000,  # 10,000 MW * 0.5h = 5,000 MWh
        },
        {
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:30:00Z",
            "publishTime": "2026-01-01T01:00:00Z",
            "generation": 12000,  # 12,000 MW * 0.5h = 6,000 MWh
        },
    ]
    forecasts = [
        {
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2025-12-31T09:30:00Z",
            "generation": 11000,
        }
    ]
    result = calculate_analysis(actuals, forecasts, cutoff_hour=10)
    day = result["daily"][0]
    assert day["date"] == "2026-01-01"
    assert day["actualTotal"] == 11000.0  # 5,000 + 6,000 = 11,000 MWh
    assert day["forecastTotal"] == 11000.0  # (11,000*0.5) + (11,000*0.5) = 11,000 MWh


def test_upstream_elexon_timeout():
    """Mock network timeout raises HTTP 502 with diagnostic detail."""
    _RAW_CACHE.clear()
    with patch("requests.Session.get", side_effect=requests.Timeout("Connection timed out")):
        with pytest.raises(Exception) as exc_info:
            fetch_fuelhh_actuals("2026-01", refresh=True)
        assert "502" in str(exc_info.value)
        assert "timed out" in str(exc_info.value).lower()


def test_upstream_malformed_response():
    """Mock malformed response raises HTTP 502."""
    _RAW_CACHE.clear()
    mock_resp = MagicMock()
    mock_resp.json.return_value = "invalid-not-a-list-or-dict"
    mock_resp.raise_for_status.return_value = None

    with patch("requests.Session.get", return_value=mock_resp):
        with pytest.raises(Exception) as exc_info:
            fetch_fuelhh_actuals("2026-01", refresh=True)
        assert "502" in str(exc_info.value)


def test_query_parameter_validation():
    """FastAPI rejects invalid month pattern and cutoff_hour parameters with 422."""
    resp1 = client.get("/api/analysis?month=not-a-month&cutoff_hour=10")
    assert resp1.status_code == 422

    resp2 = client.get("/api/analysis?month=2026-13&cutoff_hour=10")
    assert resp2.status_code == 422

    resp3 = client.get("/api/analysis?cutoff_hour=25")
    assert resp3.status_code == 422

    resp4 = client.get("/api/analysis?cutoff_hour=-1")
    assert resp4.status_code == 422


def test_supported_months_endpoint():
    """GET /api/supported-months returns supported delivery months and default."""
    resp = client.get("/api/supported-months")
    assert resp.status_code == 200
    data = resp.json()
    assert "supportedMonths" in data
    assert "defaultMonth" in data
    assert data["defaultMonth"] == "2026-01"
    assert "2026-01" in data["supportedMonths"]
    assert "2025-12" in data["supportedMonths"]
    assert "2026-02" in data["supportedMonths"]


def test_unsupported_month_rejection():
    """GET /api/analysis with an unsupported month returns HTTP 400 with detail."""
    resp = client.get("/api/analysis?month=2030-01&cutoff_hour=10")
    assert resp.status_code == 400
    assert "not currently supported" in resp.json()["detail"]


def test_february_2026_grid_calculation():
    """February 2026 has 28 days = 1,344 half-hourly settlement periods."""
    result = calculate_analysis([], [], cutoff_hour=10, month="2026-02")
    assert result["month"] == "2026-02"
    assert len(result["rows"]) == 1344
    assert result["counts"]["expectedPeriods"] == 1344
    assert result["rows"][0]["settlementDate"] == "2026-02-01"
    assert result["rows"][-1]["settlementDate"] == "2026-02-28"
    assert "February 2026" in result["methodology"]


def test_december_2025_grid_calculation():
    """December 2025 has 31 days = 1,488 half-hourly settlement periods."""
    result = calculate_analysis([], [], cutoff_hour=10, month="2025-12")
    assert result["month"] == "2025-12"
    assert len(result["rows"]) == 1488
    assert result["counts"]["expectedPeriods"] == 1488
    assert result["rows"][0]["settlementDate"] == "2025-12-01"
    assert result["rows"][-1]["settlementDate"] == "2025-12-31"
    assert "December 2025" in result["methodology"]


def test_month_selection_cutoff_continuity():
    """D-1 cutoff logic continues to function seamlessly across month transitions."""
    # Delivery on Feb 1, 2026 at 00:00 UTC -> Cutoff is Jan 31, 2026 at 10:00 UTC
    delivery = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    cutoff = cutoff_for_delivery(delivery, cutoff_hour=10)
    assert cutoff == datetime(2026, 1, 31, 10, 0, tzinfo=UTC)

    # Forecast published before cutoff on Jan 31 is accepted
    forecasts = [
        {
            "startTime": "2026-02-01T00:00:00Z",
            "publishTime": "2026-01-31T09:30:00Z",
            "generation": 8200,
        }
    ]
    actuals = [
        {
            "fuelType": "WIND",
            "startTime": "2026-02-01T00:00:00Z",
            "publishTime": "2026-02-01T00:30:00Z",
            "generation": 7900,
        }
    ]
    res = calculate_analysis(actuals, forecasts, cutoff_hour=10, month="2026-02")
    feb1_sp1 = res["rows"][0]
    assert feb1_sp1["settlementDate"] == "2026-02-01"
    assert feb1_sp1["settlementPeriod"] == 1
    assert feb1_sp1["forecastMW"] == 8200
    assert feb1_sp1["actualMW"] == 7900
    assert feb1_sp1["errorMW"] == 300


def test_caching_behavior():
    """Second call uses cache and does not invoke requests.Session.get."""
    _RAW_CACHE.clear()
    mock_data = [
        {
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2026-01-01T00:30:00Z",
            "generation": 1000,
        }
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_data
    mock_resp.raise_for_status.return_value = None

    with patch("requests.Session.get", return_value=mock_resp) as mock_get:
        # First call fetches
        res1 = fetch_fuelhh_actuals("2026-01", refresh=False)
        assert len(res1) == 1
        assert mock_get.call_count == 1

        # Second call hits cache
        res2 = fetch_fuelhh_actuals("2026-01", refresh=False)
        assert len(res2) == 1
        assert mock_get.call_count == 1  # No additional network call
