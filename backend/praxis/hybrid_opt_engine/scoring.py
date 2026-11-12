"""
Seleccion de "la mejor" ruta candidata con el modelo real HistGradientBoosting
(`scoring_policy_v2`, Capa 2 -- registrado en `artifacts` como CANDIDATE,
ver db/init/006_seed_scoring_policy_v2.sql). Porta la logica de
Pipeline_Candidatas_HGB (`1_calcular_variables_candidatas.py` +
`2_puntuar_con_histgradientboosting.py`) al pool de candidatas de
`candidate_routes.py`.

Variables del modelo (`Bp, Ceff, Cpf, V`, ver modelo_arboles_experimento.json
original / data/models/scoring_policy_v2.json):
  - Bp   : profit escalado 0-1 (MinMaxScaler) dentro del subconjunto de candidatas.
  - Cpf  : 1 - ease_of_completing.
  - Ceff : distancia de route_eff (data/reference/route_eff.parquet) a la
           media de eficiencia (3.5), acotada a 1.0.
  - V    : V_final del destino (v_final.py: shrinkage de Buhlmann de 3
           niveles sobre la ventana rodante de reportes diarios), escalado 0-1.

Reemplaza la seleccion por sort_by=profit/mileage de candidate_routes.py:
`get_best_route()` es ahora la forma recomendada de pedir "la mejor ruta"
para una consulta.

No reentrena nada -- el modelo ya viene entrenado (joblib). Para reentrenar o
explorar otros modelos, usar el repositorio original (Pipeline_Nuevo_Modelo_Rutas).
"""
import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from . import candidate_routes
from .v_final import DIAS_ES, K_SHRINKAGE, calcular_v_final, construir_detalle_rutas

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
ROUTE_EFF_PATH = _DATA_DIR / "reference" / "route_eff.parquet"
MODEL_PATH = _DATA_DIR / "models" / "scoring_policy_v2.joblib"
MODEL_META_PATH = _DATA_DIR / "models" / "scoring_policy_v2.json"

CHANCE_OF_COMPLETION_THRESHOLDS = [80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 0.0]

EFF_MEAN = 3.5
EFF_STD = 0.5
EFF_NUM_STDS = 2.0
EFF_MAX_VAL = 1.0

V_SEMANAS_TRAIN_DEFAULT = 3
EQUIP_TARGET_V_DEFAULT = "REEFER"  # igual que el pipeline original: V siempre se calcula para REEFER


@lru_cache(maxsize=1)
def _load_model():
    with open(MODEL_META_PATH, encoding="utf-8") as f:
        metricas = json.load(f)
    modelo = joblib.load(MODEL_PATH)
    return modelo, metricas["variables"], metricas


@lru_cache(maxsize=1)
def _load_route_eff() -> dict:
    """route_id (int) -> eff."""
    df = pd.read_parquet(ROUTE_EFF_PATH, columns=["route_id", "eff"])
    route_ids = pd.to_numeric(df["route_id"], errors="coerce")
    eff_vals = pd.to_numeric(df["eff"], errors="coerce")
    temp = pd.DataFrame({"route_id_num": route_ids, "eff": eff_vals}).dropna(subset=["route_id_num"])
    return temp.drop_duplicates(subset=["route_id_num"]).set_index("route_id_num")["eff"].to_dict()


@lru_cache(maxsize=1)
def _detalle_rutas_v() -> pd.DataFrame:
    return construir_detalle_rutas()


def _filtrar_por_chance_of_completion(candidatas: pd.DataFrame) -> pd.DataFrame:
    if "chance_of_completion" not in candidatas.columns:
        return candidatas
    chance = pd.to_numeric(candidatas["chance_of_completion"], errors="coerce")
    for umbral in CHANCE_OF_COMPLETION_THRESHOLDS:
        filtradas = candidatas[chance > umbral]
        if not filtradas.empty:
            return filtradas.copy()
    return candidatas.iloc[0:0].copy()


def _v_final_mapping(fecha_inicio, v_k: int = K_SHRINKAGE, v_semanas_train: int = V_SEMANAS_TRAIN_DEFAULT) -> dict:
    """(origin, equip, dia_semana) -> V_scaled para la fecha de consulta."""
    detalle = _detalle_rutas_v()
    if detalle.empty:
        return {}

    tabla = calcular_v_final(detalle, fecha_corte=fecha_inicio, k=v_k, semanas_train=v_semanas_train)

    tabla["V_scaled"] = np.nan
    for _, grp in tabla.groupby("Equip", observed=True):
        if len(grp) > 0:
            scaler = MinMaxScaler()
            tabla.loc[grp.index, "V_scaled"] = scaler.fit_transform(grp[["V_final"]]).flatten()

    tabla["origin_norm"] = tabla["Origin"].astype(str).str.strip().str.upper()
    tabla["equip_norm"] = tabla["Equip"].astype(str).str.strip().str.upper()

    return (
        tabla.dropna(subset=["V_scaled"])
        .set_index(["origin_norm", "equip_norm", "Dia"])["V_scaled"]
        .to_dict()
    )


def _calcular_variables(
    candidatas: pd.DataFrame,
    fecha_inicio,
    equip_target_v: str = EQUIP_TARGET_V_DEFAULT,
    v_k: int = K_SHRINKAGE,
    v_semanas_train: int = V_SEMANAS_TRAIN_DEFAULT,
) -> pd.DataFrame:
    """Agrega Bp, Cpf, Ceff, V a `candidatas` (mismas formulas que
    Pipeline_Candidatas_HGB/1_calcular_variables_candidatas.py)."""
    candidatas = candidatas.copy()
    candidatas["route_id_num"] = pd.to_numeric(candidatas["route_id"], errors="coerce")

    # Bp: MinMaxScaler sobre los profits del subconjunto filtrado
    profits_num = pd.to_numeric(candidatas["profit"], errors="coerce")
    valid_profits = profits_num.dropna()
    if len(valid_profits) > 0:
        scaler_bp = MinMaxScaler()
        scaler_bp.fit(valid_profits.values.reshape(-1, 1))
        candidatas["Bp"] = scaler_bp.transform(profits_num.fillna(valid_profits.min()).values.reshape(-1, 1)).flatten()
        candidatas.loc[profits_num.isna(), "Bp"] = np.nan
    else:
        candidatas["Bp"] = np.nan

    # Cpf: 1 - ease_of_completing
    eoc = pd.to_numeric(candidatas["ease_of_completing"], errors="coerce")
    candidatas["Cpf"] = 1.0 - eoc

    # Ceff: distancia de eff a la media, acotada a 1.0
    mapeo_eff = _load_route_eff()
    denominador_eff = EFF_NUM_STDS * EFF_STD
    eff_series = candidatas["route_id_num"].map(mapeo_eff)
    distancia_eff = (eff_series - EFF_MEAN).abs()
    candidatas["Ceff"] = distancia_eff.apply(
        lambda d: min(EFF_MAX_VAL, (d / denominador_eff) * EFF_MAX_VAL) if pd.notna(d) else np.nan
    )

    # V: V_final del destino (shrinkage de Buhlmann), escalado 0-1
    v_map = _v_final_mapping(fecha_inicio, v_k=v_k, v_semanas_train=v_semanas_train)
    dia_semana = DIAS_ES[pd.Timestamp(fecha_inicio).dayofweek]
    equip_target_v_norm = equip_target_v.strip().upper()
    dest_norm = candidatas["destination"].astype(str).str.strip().str.upper()
    candidatas["V"] = dest_norm.apply(lambda d: v_map.get((d, equip_target_v_norm, dia_semana), np.nan))

    for col in ["Bp", "Cpf", "Ceff", "V"]:
        candidatas[col] = pd.to_numeric(candidatas[col], errors="coerce").fillna(0.0)

    return candidatas


def score_candidates(
    zone_actual_code: str,
    equip_type: str,
    fecha_inicio: str = None,
    equip_target_v: str = EQUIP_TARGET_V_DEFAULT,
    duracion_min_dias: int = 5,
    duracion_max_dias: int = 9,
) -> pd.DataFrame:
    """
    Candidatas de `zone_actual_code` + `equip_type` para `fecha_inicio`
    (por defecto, el dia mas reciente disponible), con las variables del
    modelo (Bp, Ceff, Cpf, V) y su `probabilidad` segun scoring_policy_v2,
    ordenadas desc por probabilidad. DataFrame vacio si no hay candidatas.

    duracion_min_dias / duracion_max_dias: rango de "days" de la ruta
    candidata (viene del campo "Route duration" del formulario Create route,
    ver restricciones_y_objetivos en decision_ledger.py). Default 5-9 si no
    se especifica (comportamiento previo a que el formulario lo mandara).
    """
    fecha_str = fecha_inicio or candidate_routes.latest_date_available()
    df = candidate_routes._load_routes_for_date(fecha_str)

    dur_min = duracion_min_dias if duracion_min_dias is not None else 5
    dur_max = duracion_max_dias if duracion_max_dias is not None else 9

    equip_str = equip_type.strip().upper()
    df_days = pd.to_numeric(df["days"], errors="coerce")
    mask = (df["origin"] == zone_actual_code) & (df["equip"].astype(str).str.strip().str.upper() == equip_str) & (df_days.between(dur_min, dur_max))
    candidatas = df[mask].copy()
    if candidatas.empty:
        return candidatas

    candidatas = _filtrar_por_chance_of_completion(candidatas)
    if candidatas.empty:
        return candidatas

    candidatas = _calcular_variables(candidatas, fecha_str, equip_target_v=equip_target_v)

    modelo, variables, _ = _load_model()
    candidatas["probabilidad"] = modelo.predict_proba(candidatas[variables].to_numpy())[:, 1]
    return candidatas.sort_values("probabilidad", ascending=False).reset_index(drop=True)


def candidates_to_ledger_rows(candidatas: pd.DataFrame) -> list:
    """
    Convierte el resultado de score_candidates() (DataFrame ordenado desc por
    probabilidad) a una lista de dicts planos, uno por candidata evaluada,
    lista para decision_ledger.save_decision_candidates(). rank_posicion=1
    es la candidata recomendada (fue_elegido=True).
    """
    if candidatas is None or candidatas.empty:
        return []

    rows = []
    for rank, (_, row) in enumerate(candidatas.iterrows(), start=1):
        profit = row.get("profit")
        rows.append({
            "route_id": str(int(row["route_id"])),
            "rank_posicion": rank,
            "fue_elegido": rank == 1,
            "puntaje": float(row["probabilidad"]),
            "profit_estimado": float(profit) if pd.notna(profit) else None,
            "lanes": candidate_routes._parse_legs(row["lanes_detailed_json"]),
            "scores_detalle": {
                "Bp": float(row["Bp"]),
                "Cpf": float(row["Cpf"]),
                "Ceff": float(row["Ceff"]),
                "V": float(row["V"]),
            },
        })
    return rows


def get_best_route(zone_actual_code: str, equip_type: str, fecha_inicio: str = None):
    """
    La ruta recomendada por scoring_policy_v2 (HistGradientBoosting) para
    `zone_actual_code` + `equip_type`, o None si no hay candidatas. Mismo
    formato que candidate_routes.get_candidate_routes(), mas `probabilidad_hgb`
    y `n_candidatas`.
    """
    puntuadas = score_candidates(zone_actual_code, equip_type, fecha_inicio=fecha_inicio)
    if puntuadas.empty:
        return None

    mejor = puntuadas.iloc[0]
    route = {
        "route_id": int(mejor["route_id"]),
        "legs": candidate_routes._parse_legs(mejor["lanes_detailed_json"]),
        "probabilidad_hgb": float(mejor["probabilidad"]),
        "n_candidatas": len(puntuadas),
    }
    for field in candidate_routes._ROUTE_FIELDS:
        value = mejor[field]
        route[field] = float(value) if isinstance(value, float) else value
    return route
