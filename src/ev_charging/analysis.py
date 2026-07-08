"""Funciones de análisis sobre estaciones y ocupación.

Cada función recibe y devuelve DataFrames — sin estado, fácil de testear.
"""

from __future__ import annotations

import re

import pandas as pd


class ChargingAnalyzer:
    """Agrupa los análisis del proyecto sobre un set de estaciones + ocupación.

    Uso:
        >>> analyzer = ChargingAnalyzer(stations_df, occupancy_df)
        >>> analyzer.occupancy_by_hour()
    """

    def __init__(
        self, stations: pd.DataFrame, occupancy: pd.DataFrame | None = None
    ) -> None:
        self.stations = stations
        self.occupancy = occupancy

    # --- Infraestructura ---------------------------------------------------

    def stations_by_region(self) -> pd.DataFrame:
        """Conteo de estaciones y potencia media por región/estado."""
        return (
            self.stations.groupby("state", dropna=False)
            .agg(
                n_stations=("station_id", "count"),
                total_connectors=("n_connectors", "sum"),
                avg_power_kw=("max_power_kw", "mean"),
            )
            .sort_values("n_stations", ascending=False)
            .round(1)
        )

    def operator_share(self) -> pd.Series:
        """Participación de mercado por operador (% de estaciones)."""
        share = self.stations["operator"].fillna("(sin dato)").value_counts(normalize=True)
        return (share * 100).round(1)

    def power_distribution(self) -> pd.DataFrame:
        """Clasifica estaciones por tipo de carga según potencia máxima."""
        bins = [0, 22, 50, 150, float("inf")]
        labels = ["AC lenta (≤22kW)", "AC/DC media (≤50kW)", "DC rápida (≤150kW)", "DC ultra (>150kW)"]
        out = self.stations.copy()
        out["charge_class"] = pd.cut(out["max_power_kw"], bins=bins, labels=labels)
        return out["charge_class"].value_counts().to_frame("n_stations")

    # --- Precios ------------------------------------------------------------

    @staticmethod
    def parse_price_clp_kwh(usage_cost: str | None) -> float | None:
        """Extrae precio CLP/kWh de un string libre de OCM (ej. '$250/kWh').

        OCM guarda el costo como texto libre — este parser cubre los formatos
        comunes en Chile. Devuelve None si no es parseable.
        """
        if not usage_cost or not isinstance(usage_cost, str):
            return None
        match = re.search(r"\$?\s*([\d.,]+)\s*(?:CLP)?\s*/\s*kwh", usage_cost, re.IGNORECASE)
        if not match:
            return None
        raw = match.group(1).replace(".", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if 10 <= value <= 5000 else None  # sanity check CLP/kWh

    def price_summary(self) -> pd.DataFrame:
        """Estadísticas de precio por operador (solo estaciones con precio parseable)."""
        df = self.stations.copy()
        df["price_clp_kwh"] = df["usage_cost"].apply(self.parse_price_clp_kwh)
        priced = df.dropna(subset=["price_clp_kwh"])
        if priced.empty:
            return pd.DataFrame()
        return (
            priced.groupby("operator")["price_clp_kwh"]
            .agg(["count", "mean", "min", "max"])
            .round(0)
            .sort_values("mean")
        )

    # --- Ocupación (requiere occupancy) --------------------------------------

    def _require_occupancy(self) -> pd.DataFrame:
        if self.occupancy is None or self.occupancy.empty:
            raise ValueError("No hay datos de ocupación cargados.")
        return self.occupancy

    def occupancy_by_hour(self) -> pd.DataFrame:
        """Tasa de ocupación media por hora del día, semana vs fin de semana."""
        occ = self._require_occupancy().copy()
        occ["hour"] = occ["timestamp"].dt.hour
        occ["is_weekend"] = occ["timestamp"].dt.dayofweek >= 5
        return (
            occ.groupby(["hour", "is_weekend"])["occupancy_rate"]
            .mean()
            .unstack("is_weekend")
            .rename(columns={False: "weekday", True: "weekend"})
            .round(3)
        )

    def peak_hours(self, top_n: int = 3) -> pd.DataFrame:
        """Las N horas de mayor ocupación media."""
        occ = self._require_occupancy().copy()
        occ["hour"] = occ["timestamp"].dt.hour
        return (
            occ.groupby("hour")["occupancy_rate"]
            .mean()
            .nlargest(top_n)
            .round(3)
            .to_frame("avg_occupancy")
        )

    def saturated_stations(self, threshold: float = 0.8) -> pd.DataFrame:
        """Estaciones cuya ocupación media en horas peak supera el umbral.

        Candidatas a ampliación de capacidad — el insight accionable del proyecto.
        """
        occ = self._require_occupancy().copy()
        occ["hour"] = occ["timestamp"].dt.hour
        peak = occ[occ["hour"].isin([8, 9, 18, 19, 20])]
        by_station = peak.groupby("station_id")["occupancy_rate"].mean()
        saturated = by_station[by_station >= threshold].to_frame("peak_occupancy")
        return saturated.join(
            self.stations.set_index("station_id")[["name", "town", "operator"]]
        ).sort_values("peak_occupancy", ascending=False).round(3)
