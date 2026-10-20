# Grid forecasts under extreme weather

**Research question.** How much does using observed weather, instead of the
weather forecasts actually available a day ahead, overstate day ahead
electricity demand forecast accuracy? Is the overstatement larger on
extreme temperature days, when accuracy matters most?

Hypotheses, design choices and their reasons are in [DECISIONS.md](DECISIONS.md).

> **Status:** Milestone 2 in progress. EIA-930 data downloaded and validated:
> 8 regions pass the quality gates ([report](reports/data_quality/eia930_quality.csv),
> decision D13). Weather data is next. No modeling results yet.

## Data

| Source | What | License / terms |
|---|---|---|
| [EIA-930 Hourly Electric Grid Monitor](https://www.eia.gov/electricity/gridmonitor/) | Hourly demand and operators' day-ahead demand forecasts per balancing authority | U.S. government data, public domain |
| Open-Meteo (Milestone 2, part B) | Observed and archived forecast weather | CC BY 4.0, attribution required |

No data is committed. Scripts download it into `data/` (git-ignored), and
`data/raw/eia930/manifest.json` records a SHA-256 checksum of each file,
because EIA revises historical files.

## Reproduce

Requires [uv](https://docs.astral.sh/uv/). It installs the pinned Python and
package versions from `uv.lock`.

```bash
uv sync                          # create the environment
uv run python -m gfe.eia930      # download EIA-930 (~550 MB) and build the hourly table
uv run python -m gfe.validate    # data-quality report + region pass/fail gates
uv run pytest                    # tests
```

## Layout

```
config/study.toml   all study settings (regions, dates, quality gates)
src/gfe/            reusable code
tests/              unit tests
reports/            small generated outputs that are committed
DECISIONS.md        decision log
```
