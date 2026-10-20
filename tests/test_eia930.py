"""Tests for reading EIA-930 files. They use a tiny hand-made CSV in the same
format as the real files, so they run offline in milliseconds."""

import pandas as pd
import pytest

from gfe.eia930 import build_hourly, file_ids, read_six_month_file

HEADER = (
    '"Balancing Authority","Data Date","Hour Number","Local Time at End of Hour",'
    '"UTC Time at End of Hour","Demand Forecast (MW)","Demand (MW)",'
    '"Net Generation (MW)","Demand (MW) (Imputed)","Demand (MW) (Adjusted)","Region"\n'
)
ROWS = [
    # Thousands separators, as EIA sometimes writes large values.
    'PJM,01/01/2024,1,01/01/2024 1:00:00 AM,01/01/2024 6:00:00 AM,"83,761","85,298","92,042",,"85,298",MIDA\n',
    # Raw demand missing; EIA filled it via imputation.
    "PJM,01/01/2024,2,01/01/2024 2:00:00 AM,01/01/2024 7:00:00 AM,82791,,91438,85006,85006,MIDA\n",
    # A region outside the study, which must be filtered out.
    "AECI,01/01/2024,1,01/01/2024 1:00:00 AM,01/01/2024 7:00:00 AM,3216,3045,2903,,3045,MIDW\n",
    # PM hour, to check 12-hour clock parsing.
    "PJM,01/01/2024,14,01/01/2024 2:00:00 PM,01/01/2024 7:00:00 PM,90000,91000,95000,,91000,MIDA\n",
]


@pytest.fixture
def sample_file(tmp_path):
    path = tmp_path / "EIA930_BALANCE_2024_Jan_Jun.csv"
    path.write_text(HEADER + "".join(ROWS))
    return path


def test_file_ids_spans_years_inclusively():
    assert file_ids((2020, "Jul_Dec"), (2022, "Jan_Jun")) == [
        (2020, "Jul_Dec"), (2021, "Jan_Jun"), (2021, "Jul_Dec"), (2022, "Jan_Jun"),
    ]


def test_read_filters_regions_and_renames(sample_file):
    df = read_six_month_file(sample_file, ["PJM"])
    assert set(df["ba"]) == {"PJM"}
    assert {"ts_utc", "forecast_mw", "demand_mw", "demand_raw_mw"} <= set(df.columns)


def test_thousands_separators_become_numbers(sample_file):
    df = read_six_month_file(sample_file, ["PJM"])
    assert df["forecast_mw"].iloc[0] == 83761
    assert df["demand_mw"].iloc[0] == 85298


def test_timestamps_are_utc_and_use_12_hour_clock(sample_file):
    df = read_six_month_file(sample_file, ["PJM"])
    assert str(df["ts_utc"].dt.tz) == "UTC"
    assert df["ts_utc"].iloc[-1] == pd.Timestamp("2024-01-01 19:00", tz="UTC")


def test_imputed_hours_are_flagged(sample_file):
    df = build_hourly([sample_file], ["PJM"])
    imputed = df.loc[df["is_eia_imputed"]]
    assert len(imputed) == 1
    assert pd.isna(imputed["demand_raw_mw"].iloc[0])
    assert imputed["demand_mw"].iloc[0] == 85006


def test_renamed_eia_column_fails_loudly(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(HEADER.replace("Demand Forecast (MW)", "DF (MW)") + ROWS[0])
    with pytest.raises(ValueError):
        read_six_month_file(path, ["PJM"])
