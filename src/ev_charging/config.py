"""Configuración central del proyecto. Lee variables desde .env — nunca hardcodear secrets."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Rutas
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"

# API OpenChargeMap
OCM_BASE_URL = "https://api.openchargemap.io/v3"
OCM_API_KEY = os.getenv("OCM_API_KEY", "")

# Parámetros por defecto
COUNTRY_CODE = "CL"
DEFAULT_MAX_RESULTS = 5000  # Chile tiene ~1-2k POIs en OCM; esto cubre todo el país
REQUEST_TIMEOUT = 30  # segundos
MAX_RETRIES = 3
BACKOFF_FACTOR = 2  # espera exponencial: 2s, 4s, 8s


def ensure_dirs() -> None:
    """Crea los directorios de datos si no existen."""
    for d in (RAW_DATA_DIR, PROCESSED_DATA_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
