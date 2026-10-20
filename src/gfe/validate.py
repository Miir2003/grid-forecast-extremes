"""Data-quality report for the EIA-930 hourly table, with pass/fail gates.

Usage:
    uv run python -m gfe.validate

Reads  data/interim/eia930_hourly.parquet
Writes reports/data_quality/eia930_quality.csv (one row per region)

The gates come from config/study.toml and were fixed before this ran (D10).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gfe import DATA_DIR, REPORTS_DIR, load_config

IN_PATH = DATA_DIR / "interim" / "eia930_hourly.parquet"
OUT_PATH = REPORTS_DIR / "data_quality" / "eia930_quality.csv"
RATIO_BOUNDS = (0.5, 2.0)  # forecast/demand outside this is physically implausible


def longest_run(mask: pd.Series) -> int:
    """Length of the longest stretch of consecutive True values."""
    values = mask.to_numpy(dtype=bool)
    if not values.any():
        return 0
    # Pad with False, then find where runs start (+1) and end (-1).
    edges = np.diff(np.concatenate([[0], values.astype(int), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    return int((ends - starts).max())


def region_quality(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Quality metrics for one region over [start, end] (hour-ending, UTC)."""
    df = df[(df["ts_utc"] >= start) & (df["ts_utc"] <= end)]
    n_duplicates = int(df["ts_utc"].duplicated().sum())

    # Reindex onto a complete hourly grid so missing rows become visible NaNs.
    grid = pd.date_range(start, end, freq="h", tz="UTC")
    g = df.drop_duplicates("ts_utc", keep="last").set_index("ts_utc").reindex(grid)
    n = len(grid)

    f, d = g["forecast_mw"], g["demand_mw"]
    both = f.notna() & d.notna() & (f > 0) & (d > 0)
    ratio = f[both] / d[both]
    pct_err = 100 * (f[both] - d[both]) / d[both]

    # Adjusted demand should equal the raw value, or EIA's imputed value.
    explained = np.isclose(d, g["demand_raw_mw"]) | np.isclose(d, g["demand_imputed_mw"])

    return {
        "hours_expected": n,
        "pct_rows_missing": 100 * g["ba"].isna().mean(),
        "n_duplicate_hours": n_duplicates,
        "pct_demand_missing": 100 * d.isna().mean(),
        "pct_demand_eia_imputed": 100 * g["is_eia_imputed"].eq(True).mean(),
        "n_adjusted_unexplained": int((d.notna() & ~explained).sum()),
        "pct_forecast_missing": 100 * f.isna().mean(),
        "max_forecast_gap_hours": longest_run(f.isna()),
        "pct_nonpositive": 100 * (((f <= 0) | (d <= 0)) & f.notna() & d.notna()).mean(),
        "pct_ratio_implausible": 100 * ((ratio < RATIO_BOUNDS[0]) | (ratio > RATIO_BOUNDS[1])).sum() / n,
        "median_bias_pct": float(pct_err.median()),
        # Sanity check only, compared with published figures (~2-5%). Not a result.
        "operator_mape_pct": float(pct_err.abs().mean()),
    }


def apply_gates(table: pd.DataFrame, gates: dict) -> pd.DataFrame:
    """Add one pass/fail column per gate, plus an overall `passes` column."""
    t = table.copy()
    t["gate_forecast_missing"] = t["pct_forecast_missing"] <= gates["max_pct_forecast_missing"]
    t["gate_imputed"] = t["pct_demand_eia_imputed"] <= gates["max_pct_demand_eia_imputed"]
    t["gate_ratio"] = t["pct_ratio_implausible"] <= gates["max_pct_ratio_implausible"]
    t["gate_gap"] = t["max_forecast_gap_hours"] <= gates["max_forecast_gap_hours"]
    t["gate_bias"] = t["median_bias_pct"].abs() <= gates["max_abs_median_bias_pct"]
    t["passes"] = t.filter(like="gate_").all(axis=1)
    return t


def main() -> None:
    cfg = load_config()
    start = pd.Timestamp(cfg["study_window"]["start_utc"], tz="UTC")
    end = pd.Timestamp(cfg["study_window"]["end_utc"], tz="UTC")

    hourly = pd.read_parquet(IN_PATH)
    table = pd.DataFrame(
        {ba: region_quality(g, start, end) for ba, g in hourly.groupby("ba")}
    ).T
    table = apply_gates(table, cfg["quality_gates"])
    table.index.name = "ba"

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_PATH, float_format="%.3f")
    with pd.option_context("display.width", 200, "display.max_columns", 30,
                           "display.float_format", "{:.2f}".format):
        print(table)
    print(f"\nwrote {OUT_PATH.relative_to(REPORTS_DIR.parent)}")


if __name__ == "__main__":
    main()
