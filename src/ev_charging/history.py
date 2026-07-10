"""Lector del histórico de snapshots acumulados por el cron de GitHub Actions.

Los snapshots (data/snapshots/YYYY/MM/*.json.gz) son la fuente de datos REAL
del proyecto: cada uno captura el estado de la red en un momento dado.
Este módulo los convierte en series temporales analizables.
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path

import pandas as pd

from ev_charging import config

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = config.PROJECT_ROOT / "data" / "snapshots"


def load_snapshots(snapshot_dir: Path | None = None) -> pd.DataFrame:
    """Carga todos los snapshots en un DataFrame largo.

    Returns:
        DataFrame con las columnas de estación + `collected_at` (timestamp del
        snapshot). Vacío si no hay snapshots aún.
    """
    snapshot_dir = snapshot_dir or SNAPSHOT_DIR
    files = sorted(snapshot_dir.rglob("*.json.gz"))
    if not files:
        logger.info("Sin snapshots en %s (el cron los acumula cada 6h).", snapshot_dir)
        return pd.DataFrame()

    frames = []
    for path in files:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                payload = json.load(f)
            df = pd.DataFrame(payload["stations"])
            df["collected_at"] = pd.to_datetime(payload["collected_at"])
            frames.append(df)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.warning("Snapshot corrupto ignorado: %s (%s)", path, e)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    logger.info("Cargados %s snapshots (%s filas).", len(files), len(out))
    return out


def network_size_over_time(history: pd.DataFrame) -> pd.DataFrame:
    """Estaciones y conectores totales por snapshot."""
    if history.empty:
        return pd.DataFrame()
    return (
        history.groupby("collected_at")
        .agg(n_stations=("station_id", "nunique"), total_connectors=("n_connectors", "sum"))
        .sort_index()
    )


def new_stations(history: pd.DataFrame) -> pd.DataFrame:
    """Estaciones presentes en el último snapshot pero no en el primero."""
    if history.empty or history["collected_at"].nunique() < 2:
        return pd.DataFrame()
    first_t, last_t = history["collected_at"].min(), history["collected_at"].max()
    first_ids = set(history.loc[history["collected_at"] == first_t, "station_id"])
    last = history[history["collected_at"] == last_t]
    return last[~last["station_id"].isin(first_ids)][
        ["station_id", "name", "operator", "town", "max_power_kw"]
    ].reset_index(drop=True)


def operational_changes(history: pd.DataFrame) -> pd.DataFrame:
    """Estaciones cuyo estado operacional cambió entre primer y último snapshot.

    Útil para detectar estaciones caídas o recuperadas — el tipo de señal
    que un operador de red querría monitorear.
    """
    if history.empty or history["collected_at"].nunique() < 2:
        return pd.DataFrame()
    first_t, last_t = history["collected_at"].min(), history["collected_at"].max()
    first = history[history["collected_at"] == first_t].set_index("station_id")
    last = history[history["collected_at"] == last_t].set_index("station_id")
    common = first.index.intersection(last.index)
    changed = [
        {
            "station_id": sid,
            "name": last.loc[sid, "name"],
            "town": last.loc[sid, "town"],
            "was_operational": first.loc[sid, "is_operational"],
            "is_operational": last.loc[sid, "is_operational"],
        }
        for sid in common
        if first.loc[sid, "is_operational"] != last.loc[sid, "is_operational"]
    ]
    return pd.DataFrame(changed)
