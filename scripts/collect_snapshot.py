"""Collector para cron (GitHub Actions): snapshot compacto y comprimido.

Guarda data/snapshots/YYYY/MM/stations_<ts>.json.gz (~15-20 KB) para
acumular histórico de estado operacional sin engordar el repo.

Uso: python scripts/collect_snapshot.py
"""

import gzip
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ev_charging import config  # noqa: E402
from ev_charging.api_client import OpenChargeMapClient, OpenChargeMapError  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("collect_snapshot")

SNAPSHOT_DIR = config.PROJECT_ROOT / "data" / "snapshots"


def main() -> int:
    try:
        client = OpenChargeMapClient()
        stations = client.fetch_stations()
    except OpenChargeMapError as e:
        logger.error("Snapshot falló: %s", e)
        return 1

    if not stations:
        logger.error("API devolvió 0 estaciones — no se guarda snapshot.")
        return 1

    now = datetime.now(timezone.utc)
    out_dir = SNAPSHOT_DIR / now.strftime("%Y") / now.strftime("%m")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"stations_{now.strftime('%Y%m%dT%H%M%SZ')}.json.gz"

    payload = {"collected_at": now.isoformat(), "n_stations": len(stations), "stations": stations}
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    logger.info("Snapshot: %s estaciones → %s (%.1f KB)",
                len(stations), path, path.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
