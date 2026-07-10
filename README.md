# EV Charging Intelligence 🔌

![CI](https://github.com/igdope-bot/ev-charging-intelligence/actions/workflows/ci.yml/badge.svg)
![Data collection](https://github.com/igdope-bot/ev-charging-intelligence/actions/workflows/collect-data.yml/badge.svg)

Análisis de la infraestructura de carga para vehículos eléctricos en Chile: integración con API pública, recolección automática de datos cada 6 horas, análisis de ocupación, precios y patrones de uso, y dashboard interactivo publicado en GitHub Pages.

** Dashboard en vivo:** `https://igdope-bot.github.io/ev-charging-intelligence/`

**Stack:** Python 3.10+ · pandas · Plotly · requests · pytest

## Qué hace

- Descarga estaciones de carga de Chile desde la [API de OpenChargeMap](https://openchargemap.org/site/develop/api) (cubre redes Enel X, Copec Voltex y otras), con manejo de errores, reintentos y rate limiting.
- Simula ocupación horaria con patrones realistas (peaks de commute, diferencia semana/fin de semana) — ver [nota sobre datos](#nota-sobre-los-datos-de-ocupación).
- Analiza: ocupación por hora, distribución de potencia, participación por operador, precios CLP/kWh, estaciones saturadas candidatas a ampliación.
- Genera un dashboard HTML interactivo (mapa + gráficos) sin necesidad de servidor.
- **Recolección automática:** GitHub Actions ejecuta un snapshot cada 6 horas y lo commitea a `data/snapshots/` — construyendo un dataset histórico público de electrolineras en Chile que no existe en ninguna otra fuente.

## Instalación

```bash
git clone https://github.com/igdope-bot/ev-charging-intelligence.git
cd ev-charging-intelligence
pip install -r requirements.txt
cp .env.example .env   # agrega tu OCM_API_KEY (gratis, link en el archivo)
```

## Uso en 5 líneas

```python
from ev_charging import OpenChargeMapClient, ChargingAnalyzer

client = OpenChargeMapClient()
stations = client.to_dataframe(client.fetch_stations(max_results=300))
analyzer = ChargingAnalyzer(stations)
print(analyzer.stations_by_region())
```

Pipeline completo (descarga → análisis → dashboard en `reports/dashboard.html`):

```bash
python -m ev_charging --max-results 300
```

## Estructura

```
├── src/ev_charging/
│   ├── api_client.py    # Cliente OCM: retries, backoff, rate limiting
│   ├── availability.py  # Simulador de ocupación (datos sintéticos, documentado)
│   ├── history.py       # Series temporales desde los snapshots acumulados
│   ├── analysis.py      # Análisis: ocupación, precios, saturación
│   ├── dashboard.py     # Dashboard HTML con Plotly
│   └── config.py        # Configuración central (.env)
├── notebooks/01_eda.ipynb   # Análisis exploratorio
├── tests/                    # 100% offline (API mockeada)
├── scripts/collect_snapshot.py   # Collector para el cron de Actions
├── .github/workflows/            # CI (pytest) + recolección/deploy cada 6h
└── data/snapshots/               # Histórico acumulado (json.gz, ~20 KB c/u)
```

## Deploy propio (fork)

1. Crea el secret `OCM_API_KEY` en Settings → Secrets and variables → Actions.
2. Activa GitHub Pages: Settings → Pages → Source: **GitHub Actions**.
3. Ejecuta el workflow "Collect data & deploy dashboard" manualmente (Actions → Run workflow) o espera al cron.

## Tests

```bash
pytest
```

Todos los tests corren offline — la API está mockeada.

## Nota sobre los datos de ocupación

No existe fuente pública de disponibilidad en tiempo real para electrolineras en Chile (Enel X Way no expone API pública; OpenChargeMap solo entrega estado operacional estático). La ocupación horaria es **sintética**, generada con patrones documentados en `availability.py`. El diseño permite reemplazar el simulador por datos reales sin tocar el análisis: `save_snapshot()` ya acumula histórico real de OCM si se ejecuta periódicamente (cron).

## Extensiones posibles

Agregar un segundo proveedor de datos (misma interfaz `fetch_stations()`), migrar el dashboard a Streamlit reutilizando las funciones `fig_*`, o entrenar un modelo de predicción de ocupación sobre el histórico acumulado.

## Licencia

MIT
