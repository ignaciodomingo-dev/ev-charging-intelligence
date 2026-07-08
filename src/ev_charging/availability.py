"""Simulador de ocupación horaria de estaciones de carga.

⚠️ DATOS SINTÉTICOS. No existe fuente pública de disponibilidad en tiempo real
para electrolineras en Chile (Enel X Way no expone API; OCM solo da estado
operacional estático). Este módulo genera ocupación sintética con patrones
realistas para demostrar el pipeline de análisis. El diseño permite reemplazar
`generate_occupancy()` por un lector de datos reales sin tocar el resto.

Patrones modelados (basados en literatura de uso de cargadores públicos):
- Peaks de demanda: 8-10h (commute matutino) y 18-21h (retorno).
- Fines de semana: curva más plana, peak al mediodía.
- Cargadores rápidos (>50 kW): mayor rotación, ocupación más volátil.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RNG_SEED = 42  # reproducibilidad


def _base_hourly_profile(is_weekend: bool) -> np.ndarray:
    """Perfil de ocupación media (0-1) por hora del día."""
    hours = np.arange(24)
    if is_weekend:
        # campana centrada en 13h
        profile = 0.15 + 0.45 * np.exp(-((hours - 13) ** 2) / 18)
    else:
        # bimodal: 9h y 19h
        morning = 0.50 * np.exp(-((hours - 9) ** 2) / 6)
        evening = 0.65 * np.exp(-((hours - 19) ** 2) / 8)
        profile = 0.10 + morning + evening
    return np.clip(profile, 0, 1)


def generate_occupancy(
    stations: pd.DataFrame,
    days: int = 14,
    seed: int = RNG_SEED,
) -> pd.DataFrame:
    """Genera ocupación horaria sintética para cada estación.

    Args:
        stations: DataFrame con columnas station_id, n_connectors, max_power_kw.
        days: días de histórico a simular.
        seed: semilla para reproducibilidad.

    Returns:
        DataFrame largo: station_id, timestamp, occupied, capacity, occupancy_rate.
    """
    required = {"station_id", "n_connectors", "max_power_kw"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"Faltan columnas en stations: {missing}")

    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(
        end=pd.Timestamp.now().floor("h"), periods=days * 24, freq="h"
    )
    records = []
    for _, st in stations.iterrows():
        capacity = max(int(st["n_connectors"]), 1)
        is_fast = (st["max_power_kw"] or 0) > 50
        noise_scale = 0.18 if is_fast else 0.10

        for ts in timestamps:
            base = _base_hourly_profile(ts.dayofweek >= 5)[ts.hour]
            rate = np.clip(base + rng.normal(0, noise_scale), 0, 1)
            occupied = rng.binomial(capacity, rate)
            records.append(
                {
                    "station_id": st["station_id"],
                    "timestamp": ts,
                    "occupied": occupied,
                    "capacity": capacity,
                    "occupancy_rate": occupied / capacity,
                }
            )
    return pd.DataFrame(records)
