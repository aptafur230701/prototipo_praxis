"""
Resuelve destino_final (texto libre, ej. "Dallas, TX") al codigo de zona de
efRouting mas cercano, usando backend/data/reference/zones_id.xlsx (999
zonas con sus coordenadas: zone_id, Zone_name, lat, lng, ...).

Geocodifica el texto con Nominatim (OpenStreetMap, gratis, sin API key) y
busca la zona mas cercana por distancia haversine. Nominatim pide maximo 1
request/seg y, para uso pesado, recomienda self-hostear o usar un geocoder
de pago (Mapbox/Google) -- para este flujo (una geocodificacion por ruta
creada) alcanza, con cache en memoria para no repetir la misma ciudad.
"""
import math
from functools import lru_cache
from pathlib import Path

import openpyxl
import requests

ZONES_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "zones_id.xlsx"

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "efRouting-Praxis/1.0 (dev, contacto: equipo efRouting)"


@lru_cache(maxsize=1)
def _load_zones():
    wb = openpyxl.load_workbook(ZONES_PATH, read_only=True, data_only=True)
    ws = wb["zones id"]
    zones = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        zone_id, name, lat, lng = row[0], row[1], row[2], row[3]
        if zone_id is None or lat is None or lng is None:
            continue
        zones.append({"zone_id": zone_id, "name": name, "lat": float(lat), "lng": float(lng)})
    return zones


def _haversine_mi(lat1, lng1, lat2, lng2):
    r_mi = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r_mi * math.asin(math.sqrt(a))


@lru_cache(maxsize=256)
def _geocode(texto: str):
    """(lat, lng) o None. Cacheado en memoria: las mismas ciudades se repiten seguido."""
    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": texto, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": _USER_AGENT},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception:
        return None
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def resolve_zone_code(destino_final):
    if not destino_final:
        return None

    coords = _geocode(destino_final)
    if coords is None:
        return None
    lat, lng = coords

    zones = _load_zones()
    if not zones:
        return None

    nearest = min(zones, key=lambda z: _haversine_mi(lat, lng, z["lat"], z["lng"]))
    return nearest["zone_id"]
