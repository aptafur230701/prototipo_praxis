"""
Praxis / Knowledge State - Capa 1: Registro de Experiencia (Decision Ledger).

build_vector_estado() arma el contexto completo en el momento en que se crea
una ruta; save_decision_record() lo persiste en `decisions` (status inicial
PENDING_RESULT). Quien junta los bloques
(temporal/recurso/hos_restantes/mercado/restricciones_y_objetivos) y llama a
estas dos funciones es praxis/api.py.

save_decision_candidates() persiste las candidatas evaluadas por el Hybrid
Opt Engine (ver hybrid_opt_engine/scoring.py: score_candidates() +
candidates_to_ledger_rows()) para una decision ya creada. decision_results
(resultado real via Reconciler/TMS) todavia no se escribe desde aqui.
"""
import json

_DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _get_temporada(mes: int) -> str:
    """
    Placeholder simple por estacion del anio (hemisferio norte).
    Ajustar si 'temporada' en el negocio significa otra cosa
    (ej. temporada alta/baja de carga por mercado).
    """
    if mes in (12, 1, 2):
        return "invierno"
    if mes in (3, 4, 5):
        return "primavera"
    if mes in (6, 7, 8):
        return "verano"
    return "otonio"


def build_vector_estado(ahora, truck_id: str, truck: dict, hos: dict, mercado: dict, restricciones: dict) -> dict:
    """
    ahora: datetime.datetime (hora de creacion de la ruta)
    truck: dict del ELD/efRouting -- driver_id, equip_type, zone_actual, zone_actual_code, dias_fuera_de_casa
    hos: dict de Samsara GET /hos/clocks -- horas_conduccion_restantes, horas_turno_restantes, horas_ciclo_restantes, horas_break
    mercado: dict -- market_opportunity, rpm_p50_origen, precio_diesel_usd_gal
    restricciones: dict del formulario -- destino_final, destino_final_code, millas_minimas_ruta, costo_operativo, duracion_min_dias, duracion_max_dias, politica_de_decision
    """
    return {
        "temporal": {
            "dia_semana": _DIAS_SEMANA[ahora.weekday()],
            "semana_del_mes": ((ahora.day - 1) // 7) + 1,
            "temporada": _get_temporada(ahora.month),
        },
        "recurso": {
            "truck_id": truck_id,
            "driver_id": truck.get("driver_id"),
            "tipo_equipo": truck.get("equip_type"),
            "zone_actual": truck.get("zone_actual"),
            "zone_actual_code": truck.get("zone_actual_code"),
            "dias_fuera_de_casa": truck.get("dias_fuera_de_casa"),
        },
        "hos_restantes": {
            "horas_conduccion_restantes": hos.get("horas_conduccion_restantes"),
            "horas_turno_restantes": hos.get("horas_turno_restantes"),
            "horas_ciclo_restantes": hos.get("horas_ciclo_restantes"),
            "horas_break": hos.get("horas_break"),
        },
        "mercado": {
            "market_opportunity": mercado.get("market_opportunity"),
            "rpm_p50_origen": mercado.get("rpm_p50_origen"),
            "precio_diesel_usd_gal": mercado.get("precio_diesel_usd_gal"),
        },
        "restricciones_y_objetivos": {
            "destino_final": restricciones.get("destino_final"),
            "destino_final_code": restricciones.get("destino_final_code"),
            "millas_minimas_ruta": restricciones.get("millas_minimas_ruta"),
            "costo_operativo": restricciones.get("costo_operativo"),
            "duracion_min_dias": restricciones.get("duracion_min_dias"),
            "duracion_max_dias": restricciones.get("duracion_max_dias"),
            "politica_de_decision": restricciones.get("politica_de_decision"),
        },
    }


def _build_decision_id(conn, ahora, truck_id: str) -> str:
    """dec_{YYYYMMDD}_{truck_id}_{seq}, seq correlativo por truck y dia."""
    prefix = "dec_{}_{}_".format(ahora.strftime("%Y%m%d"), truck_id)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM decisions WHERE decision_id LIKE %s", (prefix + "%",))
        seq = cur.fetchone()[0] + 1
    return "{}{:03d}".format(prefix, seq)


def save_decision_record(conn, ahora, truck_id: str, vector_estado: dict) -> str:
    decision_id = _build_decision_id(conn, ahora, truck_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO decisions (decision_id, timestamp_decision, vector_estado)
            VALUES (%s, %s, %s)
            RETURNING decision_id
            """,
            (decision_id, ahora, json.dumps(vector_estado)),
        )
        decision_id = cur.fetchone()[0]
    conn.commit()
    return decision_id


def save_decision_candidates(conn, decision_id: str, rows: list) -> int:
    """
    rows: lista de dicts (ver hybrid_opt_engine.scoring.candidates_to_ledger_rows),
    una entrada por candidata evaluada para esta decision. Devuelve cuantas
    filas se insertaron (0 si `rows` esta vacia -- no hubo candidatas).
    """
    if not rows:
        return 0

    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO decision_candidates
                    (decision_id, route_id, rank_posicion, fue_elegido, puntaje, profit_estimado, lanes, scores_detalle)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id, route_id) DO NOTHING
                """,
                (
                    decision_id,
                    r["route_id"],
                    r["rank_posicion"],
                    r["fue_elegido"],
                    r["puntaje"],
                    r["profit_estimado"],
                    json.dumps(r["lanes"]),
                    json.dumps(r["scores_detalle"]),
                ),
            )
    conn.commit()
    return len(rows)
