"""Reading FMI's responses, from trimmed copies of real ones."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.fmi_open_data.session import FMIException, FMISession

FIXTURES = Path(__file__).parent / "fixtures"
QUERY = {"storedquery_id": "fmi::observations::weather::simple", "fmisid": "100971"}


def _session(monkeypatch, name: str, replace: tuple[str, str] | None = None) -> FMISession:
    content = (FIXTURES / name).read_text(encoding="utf-8")
    if replace is not None:
        content = content.replace(*replace)
    monkeypatch.setattr(FMISession, "get_document", lambda self, url: content.encode())
    return FMISession()


def test_latest_value_of_the_parameter(monkeypatch):
    result = _session(monkeypatch, "fmi_feature.xml").get_feature("eng", QUERY, "t2m", get_latest=True)

    assert result["data"] == [{"time": datetime(2026, 10, 14, 17, 0, tzinfo=UTC), "value": "11.4"}]
    assert (result["latitude"], result["longitude"]) == (60.17523, 24.94459)


def test_every_value_of_the_parameter(monkeypatch):
    result = _session(monkeypatch, "fmi_feature.xml").get_feature("eng", QUERY, "WS_10MIN", get_latest=False)

    assert [item["value"] for item in result["data"]] == ["5.0", "4.6", "4.7"]


def test_nan_is_dropped(monkeypatch):
    session = _session(monkeypatch, "fmi_feature.xml", ("<BsWfs:ParameterValue>4.7<", "<BsWfs:ParameterValue>NaN<"))

    result = session.get_feature("eng", QUERY, "ws_10min", get_latest=True)

    assert result["data"] == [{"time": datetime(2026, 10, 14, 16, 50, tzinfo=UTC), "value": "4.6"}]


@pytest.mark.parametrize(("negative_as_zero", "expected"), [(True, "0.0"), (False, "-1")])
def test_negative_one_as_zero(monkeypatch, negative_as_zero: bool, expected: str):
    session = _session(monkeypatch, "fmi_feature.xml", ("<BsWfs:ParameterValue>4.7<", "<BsWfs:ParameterValue>-1<"))

    result = session.get_feature("eng", QUERY, "ws_10min", get_latest=True, negative_as_zero=negative_as_zero)

    assert result["data"][0]["value"] == expected


def test_a_missing_element_is_an_fmi_error(monkeypatch):
    session = _session(monkeypatch, "fmi_feature.xml", ("<BsWfs:Time>2026-10-14T17:00:00Z</BsWfs:Time>", ""))

    with pytest.raises(FMIException, match="BsWfs:Time"):
        session.get_feature("eng", QUERY, "t2m", get_latest=True)


def test_a_broken_response_is_an_fmi_error(monkeypatch):
    monkeypatch.setattr(FMISession, "get_document", lambda self, url: b"<html>Service unavailable")

    with pytest.raises(FMIException, match="not valid XML"):
        FMISession().get_feature("eng", QUERY, "t2m", get_latest=True)


def test_only_queries_that_take_a_station_are_listed(monkeypatch):
    queries = _session(monkeypatch, "fmi_stored_queries.xml").list_stored_queries("eng", "::simple")

    assert queries == [
        ["fmi::forecast::harmonie::surface::point::simple", "Harmonie Surface Point Weather Forecast as simple features"],
        ["fmi::observations::weather::simple", "Instantaneous Weather Observations"],
    ]


def test_stations_with_their_municipality(monkeypatch):
    stations = _session(monkeypatch, "fmi_stations.xml").list_stations("eng")

    assert [(station["id"], station["name"], station["region"]) for station in stations] == [
        ("100971", "Helsinki Kaisaniemi", "Helsinki"),
        ("101237", "Lappeenranta lentoasema", "Lappeenranta"),
        ("101786", "Oulu lentoasema", "Oulu"),
    ]
    assert isinstance(stations[0]["latitude"], float)


def test_stations_serving_a_query(monkeypatch):
    stations = _session(monkeypatch, "fmi_coverage.xml").list_stations_for_query("eng", "fmi::observations::weather::simple", {})

    assert [(station["id"], station["name"], station["region"]) for station in stations] == [
        ("100971", "Helsinki Kaisaniemi", "Helsinki"),
        ("100996", "Helsinki Harmaja", "Helsinki"),
    ]
    assert (stations[0]["latitude"], stations[0]["longitude"]) == (60.17523, 24.94459)


def test_parameter_labels_and_units(monkeypatch):
    descriptions = _session(monkeypatch, "fmi_parameters.xml").get_parameter_descriptions("eng", "fmi::observations::weather::simple")

    assert descriptions["t2m"][1] == "°C"
    assert set(descriptions) == {"t2m", "ws_10min", "r_1h"}


def test_units(monkeypatch):
    session = _session(monkeypatch, "fmi_parameters.xml")

    assert session.get_unit("eng", "fmi::observations::weather::simple", "T2M") == "°C"
    assert session.get_unit("eng", "fmi::observations::weather::simple", "unknown") is None
    assert session.get_unit("eng", "stuk::observations::external-radiation::latest::multipointcoverage", "dr_pt10m_avg") == "µSv/h"
