"""STUK's air radionuclides: weekly samples, analysed one to four weeks after they end, each with its own nuclides.

FMI's ::latest query gives the sample analysed last, which need not be the newest one, and a nuclide below the
detection limit is left out of a sample altogether. So a sensor reads the samples of the last six weeks and shows the
nuclide's value in the newest sample that has it.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from custom_components.fmi_open_data.const import CONF_LANG, CONF_PARAMETER, CONF_QUERY_ID, CONF_TARGET, CONF_TARGET_TYPE
from custom_components.fmi_open_data.query_coordinator import get_start_time, query_params, stale_after_hours
from custom_components.fmi_open_data.session import FMISession

FIXTURES = Path(__file__).parent / "fixtures"
LATEST_QUERY = "stuk::observations::air::radionuclide-activity-concentration::latest::simple"
SAMPLES_QUERY = "stuk::observations::air::radionuclide-activity-concentration::multipointcoverage"
NOW = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)


def _measurement(parameter: str) -> dict:
    return {CONF_LANG: "fin", CONF_QUERY_ID: LATEST_QUERY, CONF_PARAMETER: parameter, CONF_TARGET_TYPE: "place", CONF_TARGET: "kotka"}


def _session(monkeypatch) -> FMISession:
    content = (FIXTURES / "stuk_air_samples.xml").read_bytes()
    monkeypatch.setattr(FMISession, "get_document", lambda self, url: content)
    return FMISession()


def test_the_samples_of_six_weeks_are_read():
    params = query_params(_measurement("Be-7"), NOW)

    assert params["storedquery_id"] == SAMPLES_QUERY
    assert params["starttime"] == (NOW - timedelta(days=42)).strftime("%Y-%m-%d%%20%H:%M:%S")
    assert params["place"] == "kotka"


# The fixture's samples in FMI's order: ending 2026-10-05 with all but Pb-210, ending 2026-10-12 with Be-7 and a NaN for
# Cs-137, and ending 2026-09-28 with all but Na-22, analysed last.
@pytest.mark.parametrize(
    ("parameter", "time", "value"),
    [
        ("Be-7", datetime(2026, 10, 12, 13, 33, tzinfo=UTC), "800.00"),
        ("cs-137", datetime(2026, 10, 5, 14, 40, tzinfo=UTC), "1.20"),
        ("Pb-210", datetime(2026, 9, 28, 9, 32, tzinfo=UTC), "250.00"),
        ("Na-22", datetime(2026, 10, 5, 14, 40, tzinfo=UTC), "0.30"),
        ("air-volume", datetime(2026, 10, 12, 13, 33, tzinfo=UTC), "128000"),
    ],
)
def test_a_nuclide_comes_from_the_newest_sample_that_has_it(monkeypatch, parameter: str, time: datetime, value: str):
    result = _session(monkeypatch).get_feature("fin", query_params(_measurement(parameter), NOW), parameter, get_latest=True)

    assert result["data"] == [{"time": time, "value": value}]
    assert (result["latitude"], result["longitude"]) == (60.48318, 26.91808)


def test_a_nuclide_in_no_sample_has_no_value(monkeypatch):
    result = _session(monkeypatch).get_feature("fin", query_params(_measurement("I-131"), NOW), "I-131", get_latest=True)

    assert result["data"] == []


def test_every_nuclide_of_the_window_is_available(monkeypatch):
    available = _session(monkeypatch).list_parameters("fin", query_params(_measurement("Na-22"), NOW, filter_parameter=False))

    assert available == [
        "air-volume",
        "Be-7",
        "Be-7-uncertainty",
        "Cs-137",
        "Cs-137-uncertainty",
        "Na-22",
        "Na-22-uncertainty",
        "Pb-210",
        "Pb-210-uncertainty",
    ]


def test_the_window_and_the_stale_limit_cover_the_slowest_analysis():
    assert get_start_time(LATEST_QUERY, NOW, {}) == NOW - timedelta(days=42)
    assert stale_after_hours(LATEST_QUERY, 120) == 42 * 24
    assert stale_after_hours(LATEST_QUERY, 2000) == 2000


def test_the_dose_rate_is_not_affected():
    query_id = "stuk::observations::external-radiation::latest::simple"
    params = query_params({**_measurement("DR_PT10M_avg"), CONF_QUERY_ID: query_id}, NOW)

    assert params["storedquery_id"] == query_id
    assert params["starttime"] is None
    assert stale_after_hours(query_id, 120) == 120
