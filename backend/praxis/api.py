"""
API minima que conecta el formulario "Create route" del frontend con el
Decision Ledger (Capa 1 de Praxis). Correr con:
    uvicorn praxis.api:app --reload --port 8000
(desde backend/, con el venv activado).
"""
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from praxis.admin import router as admin_router
from praxis.artifact_cache import get_champion_artifact_id
from praxis.db import get_connection
from praxis.decision_ledger import build_vector_estado, save_decision_candidates, save_decision_record
from praxis.hybrid_opt_engine import scoring as hybrid_scoring
from praxis.mock_context import get_hos_context, get_mercado_context, get_truck_context
from praxis.zones import resolve_zone_code

app = FastAPI(title="Praxis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # servidor de dev de Vite
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)


class DecisionRequest(BaseModel):
    truck_id: str
    origin: Optional[str] = None
    destino_final: Optional[str] = None
    costo_operativo: Optional[str] = None
    duracion_min_dias: Optional[int] = None
    duracion_max_dias: Optional[int] = None


class DecisionResponse(BaseModel):
    decision_id: str


@app.post("/decisions", response_model=DecisionResponse)
def create_decision(payload: DecisionRequest):
    conn = get_connection()
    try:
        truck = dict(get_truck_context(payload.truck_id))
        truck["zone_actual_code"] = truck.get("zone_actual_code") or resolve_zone_code(truck.get("zone_actual"))
        hos = get_hos_context(truck.get("driver_id"))
        mercado = get_mercado_context(payload.origin)
        restricciones = {
            "destino_final": payload.destino_final,
            "destino_final_code": resolve_zone_code(payload.destino_final),
            "millas_minimas_ruta": None,
            "costo_operativo": payload.costo_operativo,
            "duracion_min_dias": payload.duracion_min_dias,
            "duracion_max_dias": payload.duracion_max_dias,
            "politica_de_decision": get_champion_artifact_id(conn),
        }

        ahora = datetime.now()
        vector_estado = build_vector_estado(ahora, payload.truck_id, truck, hos, mercado, restricciones)
        decision_id = save_decision_record(conn, ahora, payload.truck_id, vector_estado)

        zone_actual_code = truck.get("zone_actual_code")
        equip_type = truck.get("equip_type")
        if zone_actual_code and equip_type:
            try:
                candidatas = hybrid_scoring.score_candidates(
                    zone_actual_code,
                    equip_type,
                    duracion_min_dias=restricciones.get("duracion_min_dias"),
                    duracion_max_dias=restricciones.get("duracion_max_dias"),
                )
                rows = hybrid_scoring.candidates_to_ledger_rows(candidatas)
                save_decision_candidates(conn, decision_id, rows)
            except FileNotFoundError as e:
                print(f"ADVERTENCIA: sin datos de Hunter Mode para generar candidatas de {decision_id}: {e}")
    finally:
        conn.close()

    return DecisionResponse(decision_id=decision_id)


@app.get("/health")
def health():
    return {"status": "ok"}
