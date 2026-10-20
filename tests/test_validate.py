"""Tests for the data-quality metrics, on small synthetic series where the
right answer can be worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from gfe.validate import apply_gates, longest_run, region_quality

START = pd.Timestamp("2024-01-01 01:00", tz="UTC")


def make_region(n=10):
    ts = pd.date_range(START, periods=n, freq="h", tz="UTC")
    return pd.DataFrame({
        "ba": "TEST",
        "ts_utc": ts,
        "forecast_mw": 100.0,
        "demand_raw_mw": 100.0,
        "demand_imputed_mw": np.nan,
        "demand_mw": 100.0,
        "is_eia_imputed": False,
    })


@pytest.mark.parametrize("values, expected", [
    ([], 0),
    ([False, False], 0),
    ([True, True, False, True], 2),
    ([False, True, True, True], 3),
])
def test_longest_run(values, expected):
    assert longest_run(pd.Series(values, dtype=bool)) == expected


def test_perfect_series_has_no_problems():
    q = region_quality(make_region(), START, START + pd.Timedelta(hours=9))
    assert q["hours_expected"] == 10
    assert q["pct_rows_missing"] == 0
    assert q["pct_forecast_missing"] == 0
    assert q["operator_mape_pct"] == 0


def test_missing_rows_are_found_by_reindexing():
    df = make_region().drop(index=[3, 4])  # two hours absent from the file
    q = region_quality(df, START, START + pd.Timedelta(hours=9))
    assert q["pct_rows_missing"] == pytest.approx(20)
    assert q["max_forecast_gap_hours"] == 2


def test_duplicates_counted_and_implausible_ratio_flagged():
    df = make_region()
    df = pd.concat([df, df.iloc[[0]]])          # one duplicated hour
    df.loc[df.index[5], "forecast_mw"] = 300.0  # forecast 3x demand
    q = region_quality(df, START, START + pd.Timedelta(hours=9))
    assert q["n_duplicate_hours"] == 1
    assert q["pct_ratio_implausible"] == pytest.approx(10)


def test_adjusted_value_not_matching_raw_or_imputed_is_flagged():
    df = make_region()
    df.loc[2, "demand_mw"] = 150.0
    q = region_quality(df, START, START + pd.Timedelta(hours=9))
    assert q["n_adjusted_unexplained"] == 1


def test_gates_fail_when_any_rule_breaks():
    table = pd.DataFrame({
        "pct_forecast_missing": [1.0, 9.0],
        "pct_demand_eia_imputed": [0.5, 0.5],
        "pct_ratio_implausible": [0.1, 0.1],
        "max_forecast_gap_hours": [5, 5],
        "median_bias_pct": [1.0, 1.0],
    }, index=["GOOD", "BAD"])
    gates = {
        "max_pct_forecast_missing": 5.0, "max_pct_demand_eia_imputed": 2.0,
        "max_pct_ratio_implausible": 0.5, "max_forecast_gap_hours": 168,
        "max_abs_median_bias_pct": 25.0,
    }
    out = apply_gates(table, gates)
    assert out.loc["GOOD", "passes"] and not out.loc["BAD", "passes"]
    assert not out.loc["BAD", "gate_forecast_missing"]
