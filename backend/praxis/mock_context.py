"""
Fuentes de datos para el vector de estado que TODAVIA no estan integradas de
verdad (ELD, Samsara, mercado). Cada funcion aqui es un placeholder que
devuelve datos de prueba con la misma forma que tendria la fuente real, para
que praxis/api.py y decision_ledger.py no tengan que cambiar cuando se
conecten las integraciones reales -- solo se reemplaza el cuerpo de estas
funciones.
"""

# Mock de ELD + tabla de efRouting (equip_type). Las claves coinciden con los
# ids de unit que ya existen en los datos de prueba del frontend (CR_UNITS /
# CR_CABIN_LIST en engine.js).
_MOCK_TRUCKS = {
    "TRK-1042": {"driver_id": "D001", "equip_type": "reefer", "zone_actual": "Houston, TX", "zone_actual_code": None, "dias_fuera_de_casa": 4},
    "TRK-2078": {"driver_id": "D003", "equip_type": "van", "zone_actual": "Dallas, TX", "zone_actual_code": None, "dias_fuera_de_casa": 2},
    "TRK-3390": {"driver_id": None, "equip_type": "van", "zone_actual": "Laredo, TX", "zone_actual_code": None, "dias_fuera_de_casa": 0},
    "5017": {"driver_id": "D001", "equip_type": "reefer", "zone_actual": "Memphis, TN", "zone_actual_code": None, "dias_fuera_de_casa": 6},
    "2201": {"driver_id": "D003", "equip_type": "van", "zone_actual": "Houston, TX", "zone_actual_code": None, "dias_fuera_de_casa": 2},
    "2058": {"driver_id": "D002", "equip_type": "reefer", "zone_actual": "Dallas, TX", "zone_actual_code": None, "dias_fuera_de_casa": 3},
}

_TRUCK_DEFAULT = {"driver_id": None, "equip_type": None, "zone_actual": None, "zone_actual_code": None, "dias_fuera_de_casa": None}


def get_truck_context(truck_id: str) -> dict:
    """TODO: reemplazar por lectura real del ELD del truck + cruce con la tabla de efRouting."""
    return _MOCK_TRUCKS.get(truck_id, _TRUCK_DEFAULT)


def get_hos_context(driver_id) -> dict:
    """TODO: reemplazar por Samsara GET /hos/clocks para el driver asociado al truck."""
    if driver_id is None:
        return {"horas_conduccion_restantes": None, "horas_turno_restantes": None, "horas_ciclo_restantes": None, "horas_break": None}
    return {"horas_conduccion_restantes": 9.5, "horas_turno_restantes": 12.0, "horas_ciclo_restantes": 45.0, "horas_break": 0.0}


def get_mercado_context(origen) -> dict:
    """TODO: fuente de mercado -- 'a definir' en el spec de Praxis. Por ahora, nulos."""
    return {"market_opportunity": None, "rpm_p50_origen": None, "precio_diesel_usd_gal": None}
