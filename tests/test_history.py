"""Tests del lector de histórico de snapshots."""

import gzip
import json

import pandas as pd
import pytest

from ev_charging.history import (
    load_snapshots,
    network_size_over_time,
    new_stations,
    operational_changes,
)


def write_snapshot(directory, ts: str, stations: list[dict]) -> None:
    path = directory / f"stations_{ts}.json.gz"
    payload = {"collected_at": ts, "n_stations": len(stations), "stations": stations}
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f)


STATION_A = {"station_id": 1, "name": "A", "operator": "Enel X", "town": "Santiago",
             "n_connectors": 2, "max_power_kw": 50, "is_operational": True}
STATION_B = {"station_id": 2, "name": "B", "operator": "Copec", "town": "Rancagua",
             "n_connectors": 4, "max_power_kw": 150, "is_operational": True}


@pytest.fixture
def snapshot_dir(tmp_path):
    write_snapshot(tmp_path, "2026-07-01T00:00:00+00:00", [STATION_A])
    write_snapshot(
        tmp_path,
        "2026-07-02T00:00:00+00:00",
        [dict(STATION_A, is_operational=False), STATION_B],
    )
    return tmp_path


def test_load_snapshots_empty_dir(tmp_path):
    assert load_snapshots(tmp_path).empty


def test_load_snapshots(snapshot_dir):
    df = load_snapshots(snapshot_dir)
    assert len(df) == 3
    assert df["collected_at"].nunique() == 2


def test_load_snapshots_skips_corrupt_file(snapshot_dir):
    (snapshot_dir / "stations_bad.json.gz").write_bytes(b"not gzip")
    df = load_snapshots(snapshot_dir)
    assert len(df) == 3  # el corrupto se ignora sin romper


def test_network_size_over_time(snapshot_dir):
    result = network_size_over_time(load_snapshots(snapshot_dir))
    assert list(result["n_stations"]) == [1, 2]
    assert list(result["total_connectors"]) == [2, 6]


def test_new_stations(snapshot_dir):
    result = new_stations(load_snapshots(snapshot_dir))
    assert len(result) == 1
    assert result.iloc[0]["station_id"] == 2


def test_operational_changes(snapshot_dir):
    result = operational_changes(load_snapshots(snapshot_dir))
    assert len(result) == 1
    row = result.iloc[0]
    assert row["station_id"] == 1
    assert row["was_operational"] and not row["is_operational"]


def test_single_snapshot_no_comparisons(tmp_path):
    write_snapshot(tmp_path, "2026-07-01T00:00:00+00:00", [STATION_A])
    history = load_snapshots(tmp_path)
    assert new_stations(history).empty
    assert operational_changes(history).empty
