"""Download EIA-930 six-month files and turn them into one tidy hourly table.

Usage:
    uv run python -m gfe.eia930            # download (skips files already present) + build
    uv run python -m gfe.eia930 --refresh  # re-download every file

Output:
    data/raw/eia930/*.csv                  untouched EIA files
    data/raw/eia930/manifest.json          URL, size, SHA-256 and timestamps per file
    data/interim/eia930_hourly.parquet     one row per (region, UTC hour)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from gfe import DATA_DIR, load_config

URL_TEMPLATE = (
    "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
    "EIA930_BALANCE_{year}_{half}.csv"
)
HALVES = ("Jan_Jun", "Jul_Dec")
TIME_FORMAT = "%m/%d/%Y %I:%M:%S %p"  # e.g. "01/01/2024 7:00:00 AM"

# EIA column name -> our column name. Only these columns are read.
COLUMNS = {
    "Balancing Authority": "ba",
    "UTC Time at End of Hour": "ts_utc",
    "Demand Forecast (MW)": "forecast_mw",
    "Demand (MW)": "demand_raw_mw",
    "Demand (MW) (Imputed)": "demand_imputed_mw",
    "Demand (MW) (Adjusted)": "demand_mw",
}

RAW_DIR = DATA_DIR / "raw" / "eia930"
OUT_PATH = DATA_DIR / "interim" / "eia930_hourly.parquet"


def file_ids(first: tuple[int, str], last: tuple[int, str]) -> list[tuple[int, str]]:
    """All (year, half) pairs from `first` to `last`, inclusive, in order."""
    ids = [(y, h) for y in range(first[0], last[0] + 1) for h in HALVES]
    start, end = ids.index(tuple(first)), ids.index(tuple(last))
    return ids[start : end + 1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(ids: list[tuple[int, str]], raw_dir: Path = RAW_DIR, refresh: bool = False) -> None:
    """Download each file (streamed to disk) and record it in manifest.json."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    for year, half in ids:
        url = URL_TEMPLATE.format(year=year, half=half)
        path = raw_dir / Path(url).name
        if path.exists() and not refresh:
            print(f"skip   {path.name} (already downloaded)")
            continue
        print(f"fetch  {path.name}")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            tmp = path.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
            tmp.rename(path)  # only a complete file gets the real name
            last_modified = r.headers.get("Last-Modified")
        manifest[path.name] = {
            "url": url,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "eia_last_modified": last_modified,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def read_six_month_file(path: Path, regions: list[str]) -> pd.DataFrame:
    """Read one EIA file, keep our regions and columns, parse UTC timestamps.

    Fails loudly if EIA renames a column, rather than silently dropping data.
    """
    df = pd.read_csv(path, usecols=list(COLUMNS), thousands=",", low_memory=False)
    df = df.rename(columns=COLUMNS)
    df = df[df["ba"].isin(regions)].copy()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], format=TIME_FORMAT, utc=True)
    df["source_file"] = path.name
    return df


def build_hourly(paths: list[Path], regions: list[str]) -> pd.DataFrame:
    """Stack the six-month files into one table sorted by region and hour."""
    df = pd.concat([read_six_month_file(p, regions) for p in paths], ignore_index=True)
    df["is_eia_imputed"] = df["demand_imputed_mw"].notna()
    return df.sort_values(["ba", "ts_utc"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="re-download every file")
    args = parser.parse_args()

    cfg = load_config()
    regions = cfg["regions"]["primary"] + cfg["regions"]["backup"]
    ids = file_ids(tuple(cfg["eia930"]["first_file"]), tuple(cfg["eia930"]["last_file"]))

    download(ids, refresh=args.refresh)
    paths = [RAW_DIR / Path(URL_TEMPLATE.format(year=y, half=h)).name for y, h in ids]
    hourly = build_hourly(paths, regions)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    hourly.to_parquet(OUT_PATH, index=False)
    print(f"wrote  {OUT_PATH.relative_to(DATA_DIR.parent)}: {len(hourly):,} rows, "
          f"{hourly['ba'].nunique()} regions, "
          f"{hourly['ts_utc'].min()} to {hourly['ts_utc'].max()}")


if __name__ == "__main__":
    main()
