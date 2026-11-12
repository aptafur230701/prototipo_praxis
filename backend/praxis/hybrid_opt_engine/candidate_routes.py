"""
Consulta del pool de rutas candidatas ya filtradas/aprobadas por Hunter Mode
(`data/hunter_mode/daily/<YYYY-MM-DD>/zones_rerouting_report.parquet`). Ese
proceso de filtrado -- factibilidad de mercado, conectividad -- es externo y
esta fuera de alcance de este modulo: aqui solo se expone su output, ya en
el sistema de zonas (`Z_1`..`Z_88`) que usa el resto de Praxis.

En produccion, Hunter Mode regenera un reporte nuevo cada dia; el backend
mantiene una ventana rodante de los ultimos dias (ver DAILY_DIR) en vez de
un solo archivo plano, porque el calculo de V_final (modulo v_final.py, que
usa `score_best_route` en scoring.py) necesita varias semanas de historico.
Por defecto, las funciones de este modulo usan el dia mas reciente
disponible en esa ventana ("hoy").

Reemplaza al pool crudo (`routes_zones.parquet`, todas las combinaciones
posibles sin filtrar), que ya no se usa para esto.

Forma del parquet: una fila por `route_id` (ruta completa, no por leg). El
detalle de cada tramo viene embebido en `lanes_detailed_json`.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

DAILY_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "hunter_mode" / "daily"
REPORT_FILENAME = "zones_rerouting_report.parquet"
_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SORT_COLUMNS = {"profit", "profit_potential", "mileage"}

_ROUTE_FIELDS = [
    "equip", "destination", "mileage", "days", "profit", "profit_potential",
    "min_revenue", "max_revenue", "rpm_min", "rpm_max",
]


def latest_date_available(daily_dir: Path = DAILY_DIR) -> str:
    """Fecha (YYYY-MM-DD) mas reciente con reporte disponible en la ventana rodante."""
    if not daily_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de reportes diarios: {daily_dir}")
    fechas = sorted(p.name for p in daily_dir.iterdir() if p.is_dir() and _DATE_DIR_RE.match(p.name))
    if not fechas:
        raise FileNotFoundError(f"No hay reportes diarios en: {daily_dir}")
    return fechas[-1]


@lru_cache(maxsize=8)
def _load_routes_for_date(fecha_str: str) -> pd.DataFrame:
    path = DAILY_DIR / fecha_str / REPORT_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"No hay reporte de Hunter Mode para la fecha {fecha_str} en: {path}")
    return pd.read_parquet(path)


def _parse_legs(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


def get_candidate_routes(
    zone_actual_code: str,
    equip_type: str = None,
    top_n: int = 10,
    sort_by: str = "profit",
    fecha_inicio: str = None,
):
    """
    Rutas candidatas (ya filtradas por Hunter Mode) que arrancan en
    `zone_actual_code`, para el reporte de `fecha_inicio` (por defecto, el
    dia mas reciente disponible). Retorna hasta `top_n` dicts, ordenados
    desc por `sort_by` ('profit' | 'profit_potential' | 'mileage'):
        {route_id, equip, destination, mileage, days, profit, profit_potential,
         min_revenue, max_revenue, rpm_min, rpm_max, legs: [...]}
    `legs` es la secuencia de tramos (origin_id/name, destination_id/name, lat/lng).
    """
    if sort_by not in _SORT_COLUMNS:
        raise ValueError("sort_by debe ser uno de: {}".format(_SORT_COLUMNS))

    fecha_str = fecha_inicio or latest_date_available()
    df = _load_routes_for_date(fecha_str)
    subset = df[df["origin"] == zone_actual_code]
    if equip_type:
        subset = subset[subset["equip"] == equip_type]
    if subset.empty:
        return []

    subset = subset.sort_values(sort_by, ascending=False).head(top_n)

    results = []
    for _, row in subset.iterrows():
        route = {"route_id": int(row["route_id"]), "legs": _parse_legs(row["lanes_detailed_json"])}
        for field in _ROUTE_FIELDS:
            value = row[field]
            route[field] = float(value) if isinstance(value, float) else value
        results.append(route)
    return results
