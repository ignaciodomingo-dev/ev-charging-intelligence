"""Cliente para la API de OpenChargeMap (https://openchargemap.org/site/develop/api).

Fuente pública de puntos de carga EV. Cubre Chile, incluyendo la red Enel X.
Requiere API key gratuita: https://openchargemap.org/site/loginprovider/register

Nota: Enel X Way no expone API pública documentada (verificado jul-2026).
Este cliente está diseñado para que agregar otro proveedor sea trivial:
implementar `fetch_stations()` con la misma salida (list[dict]) basta.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from ev_charging import config

logger = logging.getLogger(__name__)


class OpenChargeMapError(Exception):
    """Error al consultar la API de OpenChargeMap."""


class OpenChargeMapClient:
    """Cliente HTTP con reintentos y backoff exponencial.

    Uso:
        >>> client = OpenChargeMapClient()  # lee OCM_API_KEY desde .env
        >>> stations = client.fetch_stations(max_results=100)
        >>> df = client.to_dataframe(stations)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = config.OCM_BASE_URL,
        timeout: int = config.REQUEST_TIMEOUT,
        max_retries: int = config.MAX_RETRIES,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.OCM_API_KEY
        if not self.api_key:
            raise OpenChargeMapError(
                "Falta OCM_API_KEY. Copia .env.example a .env y agrega tu key "
                "(gratis en https://openchargemap.org/site/loginprovider/register)."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {"X-API-Key": self.api_key, "User-Agent": "ev-charging-intelligence/0.1"}
        )

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        """GET con reintentos. Lanza OpenChargeMapError si agota los intentos."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 429:  # rate limit: respetar y reintentar
                    wait = config.BACKOFF_FACTOR**attempt
                    logger.warning("Rate limit (429). Esperando %ss…", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                wait = config.BACKOFF_FACTOR**attempt
                logger.warning("Intento %s/%s falló (%s). Reintentando en %ss…",
                               attempt, self.max_retries, type(e).__name__, wait)
                time.sleep(wait)
            except requests.HTTPError as e:
                # 4xx (excepto 429) no se reintenta: el request está mal
                raise OpenChargeMapError(f"HTTP {resp.status_code} en {url}: {e}") from e
            except json.JSONDecodeError as e:
                raise OpenChargeMapError(f"Respuesta no es JSON válido: {e}") from e

        raise OpenChargeMapError(
            f"API no disponible tras {self.max_retries} intentos: {last_error}"
        )

    def fetch_stations(
        self,
        country_code: str = config.COUNTRY_CODE,
        max_results: int = config.DEFAULT_MAX_RESULTS,
        operator_name: str | None = None,
    ) -> list[dict]:
        """Descarga puntos de carga del país indicado.

        Args:
            country_code: ISO 3166-1 alpha-2 (default "CL").
            max_results: máximo de estaciones a traer.
            operator_name: filtra por operador (ej. "enel") post-request,
                porque OCM no soporta filtro por nombre de operador en query.
        """
        raw = self._get(
            "poi",
            {
                "countrycode": country_code,
                "maxresults": max_results,
                "compact": "true",
                "verbose": "false",
            },
        )
        if not isinstance(raw, list):
            raise OpenChargeMapError(f"Respuesta inesperada: {type(raw).__name__}")

        stations = [self._parse_station(s) for s in raw]
        if operator_name:
            needle = operator_name.lower()
            stations = [s for s in stations if needle in (s["operator"] or "").lower()]
        logger.info("Descargadas %s estaciones (%s)", len(stations), country_code)
        return stations

    @staticmethod
    def _parse_station(poi: dict) -> dict:
        """Aplana el JSON de OCM a un dict de una dimensión. Tolera campos faltantes."""
        addr = poi.get("AddressInfo") or {}
        conns = poi.get("Connections") or []
        max_power = max((c.get("PowerKW") or 0 for c in conns), default=0)
        return {
            "station_id": poi.get("ID"),
            "name": addr.get("Title"),
            "operator": (poi.get("OperatorInfo") or {}).get("Title"),
            "usage_cost": poi.get("UsageCost"),
            "latitude": addr.get("Latitude"),
            "longitude": addr.get("Longitude"),
            "town": addr.get("Town"),
            "state": addr.get("StateOrProvince"),
            "n_connectors": len(conns),
            "max_power_kw": max_power,
            "is_operational": (poi.get("StatusType") or {}).get("IsOperational"),
            "date_created": poi.get("DateCreated"),
        }

    @staticmethod
    def to_dataframe(stations: list[dict]) -> pd.DataFrame:
        """Convierte la lista de estaciones a DataFrame tipado."""
        df = pd.DataFrame(stations)
        if not df.empty:
            df["date_created"] = pd.to_datetime(df["date_created"], errors="coerce")
        return df

    def save_snapshot(self, stations: list[dict], out_dir: Path | None = None) -> Path:
        """Guarda un snapshot JSON con timestamp en data/raw/. Devuelve la ruta.

        Ejecutado periódicamente (cron), acumula histórico real de estado
        operacional — base para análisis de disponibilidad a futuro.
        """
        out_dir = out_dir or config.RAW_DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"stations_{ts}.json"
        path.write_text(json.dumps(stations, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Snapshot guardado: %s", path)
        return path
