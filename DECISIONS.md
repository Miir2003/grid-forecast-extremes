# Decision log

Every design choice that could change a result is recorded here, with the
reason and the alternatives considered. Decisions are made **before** looking at
the outcomes they affect. If a decision changes later, the old entry stays and a
new entry explains why.

## Research question

How much does using observed weather, instead of the weather forecasts that were
actually available a day ahead, overstate day-ahead electricity demand forecast
accuracy? Is the overstatement larger on extreme-temperature days?

- **H1** A model given observed weather looks more accurate than the same model
  given archived day-ahead weather forecasts. The gap is larger on extreme days.
- **H2** The error gap between an open model and the operators' own
  day-ahead forecasts is different on extreme days than on normal days
  (two-sided).
- **H3** Prediction intervals calibrated on all days under-cover on extreme
  days, and adaptive conformal inference reduces the shortfall.

## Decisions

### D1 — Regions (2026-10-20)
ERCO, PJM, MISO, CISO, ISNE, SWPP, TVA, BPAT; NYIS as backup.
**Why:** Eight large regions spanning heat-driven and cold-driven climates,
including events inside the data window (2021 Pacific NW heat dome, Winter
Storm Elliott 2022, January 2024/2025 cold). Few enough to validate by hand.
**Alternatives:** All ~40 eligible regions (more power, far more cleaning).

### D2 — Extreme-day definition (2026-10-20)
Per region, a day is extreme-hot (cold) if its population-weighted daily mean
observed temperature is above the 95th (below the 5th) percentile of the
1991–2020 climatology for that calendar period. Sensitivity at 2.5% and 10%.
**Why:** Temperature does not depend on the outcome being forecast. Defining
extremes by demand would select days because the outcome was unusual, which
biases every model's apparent error upward on those days. A fixed historical
baseline keeps thresholds independent of the study period.
**Note:** Used only to label days for evaluation, never as a model input.

### D3 — Weather representation (2026-10-20)
Population-weighted average of 3–5 metro areas per region, weights fixed at
2020 Census population. Single-city weather is kept as an ablation.
**Why:** Demand follows population. One city cannot represent MISO or PJM.

### D4 — Weather variables (2026-10-20)
Main analysis uses temperature and derived features only.
**Why:** Archived day-ahead forecasts of temperature go back to ~March 2021,
most other variables only to January 2024. Humidity/wind are a 2024+ ablation.

### D5 — Fair comparison for H1 (2026-10-20)
The observed-weather and forecast-weather models share features, locations and
algorithm, and each is trained and tested on its own weather source.

### D6 — Uncertainty for extreme-day results (2026-10-20)
Confidence intervals use a block bootstrap over weather events/weeks, not
single days, because extreme days cluster in time and across regions.

### D7 — Time handling (2026-10-20)
All data keyed on UTC hour-ending timestamps.
**Why:** Local times have daylight-saving gaps, and regions differ (MISO
reports in fixed standard time). UTC has one row per hour everywhere.

### D8 — EIA-930 source (2026-10-20)
EIA six-month bulk CSV files, not the API.
**Why:** No API key needed, so anyone can reproduce the download. Whole files
can be fingerprinted (SHA-256). EIA regenerates historical files (all were
re-dated 2026-10-19), so the manifest records the exact version we used.

### D9 — Demand target (2026-10-20)
Target is `Demand (MW) (Adjusted)`. Hours where EIA imputed demand are flagged
(`is_eia_imputed`). Checked on the 2024 H1 file: adjusted equals the reported
value, or EIA's imputed value when the report was missing; no other cases.
**Open question for Milestone 3:** exclude flagged hours from evaluation only,
or from training too.

### D10 — Region quality gates (2026-10-20, set before running validation)
A region stays in the study only if, inside the study window:
- operator forecast missing ≤ 5% of hours;
- EIA-imputed demand ≤ 2% of hours;
- forecast/demand ratio outside [0.5, 2] ≤ 0.5% of hours;
- no run of missing forecasts longer than 168 hours (one week);
- |median forecast bias| ≤ 25% (the series-mismatch rule from
  [ba-forecast-scorecard](https://github.com/cardinalgrid/ba-forecast-scorecard)).
A failing primary region is replaced by NYIS.
**Why:** Fixing the rules first stops the region list being tuned to results.

### D11 — Study end date (2026-10-20)
Study window ends 2026-09-30 (UTC).
**Why:** The newest weeks of EIA data are revised most often. Leaving a gap of
about three weeks before the download date avoids training on numbers that
are still changing.

### D12 — Study start date (2026-10-20)
Study window starts 2021-04-01 (UTC).
**Why:** Checked against the Open-Meteo Previous Runs API (GFS, Houston):
1-day-lead temperature forecasts begin 2021-03-24 and 2-day-lead forecasts
2021-03-25, with no gaps after that. April 1 is the first full month with both.
**Consequence:** Winter Storm Uri (Feb 2021) is outside the study.
**Open question for Part B:** EIA-930 does not say when operators issue their
day-ahead forecast (typically the morning of the day before). For late hours of
the target day, a 1-day-lead weather forecast may be *newer* than what the
operator had. We must pick a weather lead time per target hour so our model
never sees fresher information than the operator could have.

### D13 — Quality-gate outcome (2026-10-20)
Ran `gfe.validate` on 2021-04-01 to 2026-09-30 (48,216 hours per region).
- Passed all gates: BPAT, CISO, ERCO, ISNE, MISO, PJM, TVA, NYIS.
- **SWPP failed** the forecast-gap gate: operator forecast missing for 384
  consecutive hours (2026-08-04 to 2026-08-20). Other gates passed.
- No missing rows, no duplicate hours, and in every region adjusted demand
  equals raw or EIA-imputed demand (confirms D9 for all years, not just 2024).

**Decision:** Per D10, SWPP is replaced by NYIS. Final regions: BPAT, CISO,
ERCO, ISNE, MISO, NYIS, PJM, TVA.
**Why not keep SWPP:** The gap is recent and EIA may backfill it, which makes
an exception tempting. But changing a rule after seeing which region fails it
is exactly what fixing the rules in advance is meant to prevent.
**Cost:** The Great Plains climate is no longer represented, and NYIS overlaps
geographically with ISNE and PJM. Recorded as a limitation. SWPP may appear in
a clearly labeled exploratory robustness check only.

### D14 — Non-positive values (2026-10-20)
Demand or forecast values ≤ 0 are treated as missing. NYIS has 126 such hours
(0.26%), all exact zeros, which are physically impossible for New York.
No gate covered this, and it does not change region selection.
