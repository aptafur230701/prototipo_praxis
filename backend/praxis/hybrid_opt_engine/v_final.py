"""
V_final(zona, equipo, dia): shrinkage de Buhlmann de 3 niveles sobre el
historico de VE = (Profit/Days) * (chance_of_completion/100), portado de
Pipeline_Candidatas_HGB/calcular_v_final.py.

A diferencia del script original (que lee un .zip completo), esta version
lee la ventana rodante de reportes diarios que mantiene el backend en
`data/hunter_mode/daily/<YYYY-MM-DD>/zones_rerouting_report.parquet` (ver
candidate_routes.py). Esa ventana debe cubrir al menos las `semanas_train`
semanas calendario anteriores a la fecha de consulta -- si faltan dias,
`calcular_v_final` lanza ValueError.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

DIAS_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
ZONE_RE = re.compile(r"^Z_\d+$")
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

K_SHRINKAGE = 10  # recomendado en notebook_backtest_k.ipynb (repositorio de origen)

DAILY_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "hunter_mode" / "daily"


def construir_detalle_rutas(daily_dir: Path = DAILY_DIR) -> pd.DataFrame:
    """Lee la ventana rodante de reportes diarios y devuelve el VE de cada
    ruta individual (sin agregar), con columnas Origin, Equip, Date, Dia, VE."""
    frames = []

    for sub in sorted(daily_dir.iterdir()) if daily_dir.exists() else []:
        if not sub.is_dir() or not DATE_DIR_RE.match(sub.name):
            continue
        parquet_path = sub / "zones_rerouting_report.parquet"
        if not parquet_path.exists():
            continue

        df = pd.read_parquet(parquet_path, columns=["origin", "profit", "days", "equip", "chance_of_completion"])
        df = df[df["origin"].str.match(ZONE_RE)]
        df = df[df["days"] > 0]

        profit_per_day = df["profit"] / df["days"]
        ve = (profit_per_day * (df["chance_of_completion"] / 100.0)).astype("float32")

        out = pd.DataFrame({
            "Origin": df["origin"].to_numpy(),
            "Equip": df["equip"].to_numpy(),
            "VE": ve.to_numpy(),
        })
        out["Date"] = np.datetime64(sub.name)
        frames.append(out)

    if not frames:
        return pd.DataFrame(columns=["Origin", "Equip", "VE", "Date", "Dia"])

    detalle = pd.concat(frames, ignore_index=True)
    detalle["Origin"] = detalle["Origin"].astype("category")
    detalle["Equip"] = detalle["Equip"].astype("category")
    detalle["Dia"] = pd.Categorical(
        detalle["Date"].dt.dayofweek.map(lambda i: DIAS_ES[i]), categories=DIAS_ES,
    )
    return detalle


def ventana_entrenamiento(fecha_corte, semanas: int = 3):
    """Dada una fecha, devuelve (inicio, fin) de las `semanas` semanas
    calendario (lunes-domingo) completas inmediatamente anteriores a la
    semana que contiene `fecha_corte` (esa semana y `fecha_corte` misma
    quedan fuera, para no filtrar informacion)."""
    fecha_corte = pd.Timestamp(fecha_corte)
    lunes_semana_corte = fecha_corte - pd.Timedelta(days=fecha_corte.weekday())
    inicio = lunes_semana_corte - pd.Timedelta(days=7 * semanas)
    fin = lunes_semana_corte - pd.Timedelta(days=1)
    return inicio, fin


def shrink(n_cell, V_cell, n_zc, V_zc, n_c, V_c, k=K_SHRINKAGE):
    """Shrinkage de Buhlmann de 3 niveles. Si una celda tiene n_cell=0 cae al
    padre (zona-camion), y si ese tambien tiene n_zc=0 cae al global."""
    n_cell = np.asarray(n_cell, dtype=float)
    n_zc = np.asarray(n_zc, dtype=float)
    V_cell = np.asarray(V_cell, dtype=float)
    V_zc = np.asarray(V_zc, dtype=float)
    V_c = np.asarray(V_c, dtype=float)

    with np.errstate(invalid="ignore", divide="ignore"):
        w1 = np.where(n_cell > 0, n_cell / (n_cell + k), 0.0)
        w2 = np.where(n_zc > 0, n_zc / (n_zc + k), 0.0)

    padre = np.where(n_zc > 0, w2 * V_zc + (1 - w2) * V_c, V_c)
    return np.where(n_cell > 0, w1 * V_cell + (1 - w1) * padre, padre)


def calcular_v_final(detalle: pd.DataFrame, fecha_corte, k: int = K_SHRINKAGE, semanas_train: int = 3) -> pd.DataFrame:
    """Calcula V_final(Origin, Equip, Dia) usando las `semanas_train` semanas
    completas anteriores a la semana de `fecha_corte`.

    `detalle` debe tener columnas Origin, Equip, Date, Dia, VE (ver
    `construir_detalle_rutas`).
    """
    inicio, fin = ventana_entrenamiento(fecha_corte, semanas_train)
    train = detalle[(detalle["Date"] >= inicio) & (detalle["Date"] <= fin)]
    if train.empty:
        raise ValueError(
            f"No hay datos entre {inicio.date()} y {fin.date()} para calcular V_final "
            f"(revisa la ventana rodante en data/hunter_mode/daily/)."
        )

    cell_stats = train.groupby(["Origin", "Equip", "Dia"], observed=True)["VE"].agg(n_cell="count", V_cell="median")
    zc_stats = train.groupby(["Origin", "Equip"], observed=True)["VE"].agg(n_zc="count", V_zc="median")
    c_stats = train.groupby(["Equip"], observed=True)["VE"].agg(n_c="count", V_c="median")

    tabla = cell_stats.reset_index()
    tabla = tabla.merge(zc_stats, on=["Origin", "Equip"], how="left")
    tabla = tabla.merge(c_stats, on=["Equip"], how="left")

    tabla["V_final"] = shrink(tabla["n_cell"], tabla["V_cell"], tabla["n_zc"], tabla["V_zc"], tabla["n_c"], tabla["V_c"], k)

    return tabla[["Origin", "Equip", "Dia", "n_cell", "n_zc", "n_c", "V_cell", "V_zc", "V_c", "V_final"]].sort_values(
        ["Equip", "Dia", "V_final"], ascending=[True, True, False]
    ).reset_index(drop=True)
