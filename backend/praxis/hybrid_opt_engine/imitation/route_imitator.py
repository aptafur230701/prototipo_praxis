"""
Generador de Rutas por Imitación — v2
======================================
Aprende el comportamiento de un carrier desde datos históricos y genera
ciclos nuevos que lo imitan, filtrando por factibilidad de mercado (EoB)
y rentabilidad (RPM_Q2).

Uso:
    python route_imitator_final.py                        # usa defaults
    python route_imitator_final.py --input mis_datos.xlsx --n 1000 --seed 7
    python route_imitator_final.py --help

Columnas requeridas en el archivo de entrada:
    Zone_Origin_Code, Zone_Dest_Code, DeadHead, EoB, RPM_Q2,
    InRoute_TotalDistance, Duration_Hours, Cycle, Start_Time
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# ── Parámetros por defecto ────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "imitation"
DEFAULT_INPUT  = str(_DATA_DIR / "ciclos_con_separador_semana_rpm.xlsx")
DEFAULT_OUTPUT = str(_DATA_DIR / "rutas_imitadas_500.xlsx")
DEFAULT_N      = 500        # ciclos aceptados a generar
DEFAULT_SEED   = 42
DEFAULT_MIN_EOB = 50        # EoB mínimo por lane cargada
DEFAULT_N_LOADED = None     # None = aleatorio 3–4; pasa un entero para fijar


# ── Modelo ────────────────────────────────────────────────────────────────────
class RouteImitator:
    """
    Cadena de Markov sobre zonas, con matrices separadas para lanes
    cargadas y deadhead (metodología v2).

    Estructura generada: LOAD → [0|1 DH] → LOAD → … → LOAD
    Máximo 1 DH consecutivo entre cargas.
    """

    def fit(self, df: pd.DataFrame) -> "RouteImitator":
        """
        Aprende del historial de lanes reales.

        df debe tener: Zone_Origin_Code, Zone_Dest_Code, DeadHead,
                       InRoute_TotalDistance, Duration_Hours, Cycle, Start_Time
        """
        self.loaded_trans: dict = defaultdict(lambda: defaultdict(int))
        self.dh_trans:     dict = defaultdict(lambda: defaultdict(int))
        self.loaded_stats: dict = defaultdict(list)   # {(orig,dest): [{distance, duration}]}
        self.dh_stats:     dict = defaultdict(list)
        self.start_zones:  dict = defaultdict(int)    # distribución de inicio de ciclo
        after_load_dh:     dict = defaultdict(list)   # para aprender p_dh_after

        for cycle_id, grp in df.groupby("Cycle"):
            grp = grp.sort_values("Start_Time").reset_index(drop=True)

            # Hub de inicio: primera lane cargada del ciclo
            first_loaded = grp[grp["DeadHead"] == 0]
            if not first_loaded.empty:
                self.start_zones[first_loaded.iloc[0]["Zone_Origin_Code"]] += 1

            for idx in range(len(grp)):
                row  = grp.iloc[idx]
                orig = row["Zone_Origin_Code"]
                dest = row["Zone_Dest_Code"]
                stat = {
                    "distance": row.get("InRoute_TotalDistance"),
                    "duration": row.get("Duration_Hours"),
                }

                if int(row["DeadHead"]) == 0:
                    self.loaded_trans[orig][dest] += 1
                    self.loaded_stats[(orig, dest)].append(stat)
                    # ¿el siguiente tramo fue DH?
                    if idx + 1 < len(grp):
                        after_load_dh[dest].append(
                            int(grp.iloc[idx + 1]["DeadHead"]) == 1
                        )
                else:
                    self.dh_trans[orig][dest] += 1
                    self.dh_stats[(orig, dest)].append(stat)

        # Probabilidad de insertar un DH después de llegar a cada zona
        self.p_dh_after: dict = {
            zone: float(np.mean(vals))
            for zone, vals in after_load_dh.items()
        }
        return self

    # ── helpers ───────────────────────────────────────────────────────────────
    def _probs(self, trans: dict, zone: str):
        """Devuelve (destinos, probabilidades) desde `zone` en `trans`."""
        destinations = list(trans.get(zone, {}).keys())
        if not destinations:
            return None, None
        counts = np.array([float(trans[zone][d]) for d in destinations])
        return destinations, counts / counts.sum()

    def _sample_stat(self, stats_dict: dict, key: tuple) -> dict:
        """Muestrea aleatoriamente un registro histórico de distancia/duración."""
        records = stats_dict.get(key, [{}])
        return records[np.random.randint(len(records))]

    # ── generación ────────────────────────────────────────────────────────────
    def generate_cycle(
        self,
        eob_table: dict,
        n_loaded: int | None = None,
    ) -> list[dict]:
        """
        Genera un ciclo con `n_loaded` lanes cargadas (3–4 si None).
        Inserta a lo sumo 1 DH entre cargas consecutivas.
        """
        # Hub de inicio según distribución histórica
        zones  = list(self.start_zones.keys())
        counts = np.array(list(self.start_zones.values()), dtype=float)
        zone   = np.random.choice(zones, p=counts / counts.sum())

        target = n_loaded if n_loaded else np.random.randint(3, 5)
        route  = []

        for i in range(target):
            # Lane cargada
            dests, probs = self._probs(self.loaded_trans, zone)
            if dests is None:
                break
            next_zone = np.random.choice(dests, p=probs)
            key       = (zone, next_zone)
            stat      = self._sample_stat(self.loaded_stats, key)
            route.append({
                "Zone_Origin": zone,
                "Zone_Dest":   next_zone,
                "Lane":        f"{zone} → {next_zone}",
                "DeadHead":    0,
                "EoB":         eob_table.get(key, np.nan),
                "Distance_mi": stat.get("distance"),
                "Duration_hrs": stat.get("duration"),
            })
            zone = next_zone

            # Posible DH entre cargas (no después de la última)
            if i < target - 1:
                p_dh = self.p_dh_after.get(zone, 0.3)
                if np.random.random() < p_dh:
                    dd, dp = self._probs(self.dh_trans, zone)
                    if dd is not None:
                        dh_dest = np.random.choice(dd, p=dp)
                        dh_key  = (zone, dh_dest)
                        dh_stat = self._sample_stat(self.dh_stats, dh_key)
                        route.append({
                            "Zone_Origin": zone,
                            "Zone_Dest":   dh_dest,
                            "Lane":        f"{zone} → {dh_dest}",
                            "DeadHead":    1,
                            "EoB":         np.nan,
                            "Distance_mi": dh_stat.get("distance"),
                            "Duration_hrs": dh_stat.get("duration"),
                        })
                        zone = dh_dest
        return route

    def generate_batch(
        self,
        eob_table:  dict,
        rate_table: dict,
        n:          int   = 500,
        min_eob:    float = 50.0,
        n_loaded:   int | None = None,
        max_factor: int   = 100,
    ) -> tuple[list[dict], int]:
        """
        Genera `n` ciclos aceptados mediante rejection sampling.

        Criterios de aceptación:
            1. Todas las lanes cargadas tienen EoB ≥ min_eob.
            2. RPM_Q2 promedio del ciclo ≥ p50 global del rate_table.

        Devuelve (resultados, intentos_totales).
        """
        global_p50 = float(np.median(list(rate_table.values()))) if rate_table else 0.0
        results, attempts = [], 0

        while len(results) < n and attempts < n * max_factor:
            route    = self.generate_cycle(eob_table, n_loaded=n_loaded)
            attempts += 1
            loaded   = [lane for lane in route if lane["DeadHead"] == 0]
            if not loaded:
                continue

            # Filtro EoB
            eob_vals = [eob_table.get((l["Zone_Origin"], l["Zone_Dest"]), np.nan) for l in loaded]
            eob_vals = [v for v in eob_vals if not np.isnan(v)]
            if not eob_vals or not all(v >= min_eob for v in eob_vals):
                continue

            # Filtro RPM
            rates = [rate_table.get((l["Zone_Origin"], l["Zone_Dest"]), np.nan) for l in loaded]
            rates = [r for r in rates if not np.isnan(r)]
            if not rates or float(np.mean(rates)) < global_p50:
                continue

            results.append({
                "cycle":    route,
                "eob_avg":  float(np.mean(eob_vals)),
                "rpm_avg":  float(np.mean(rates)),
                "n_loaded": len(loaded),
                "n_dh":     sum(1 for l in route if l["DeadHead"]),
            })

        return results, attempts


# ── I/O ───────────────────────────────────────────────────────────────────────
def load_data(path: str) -> pd.DataFrame:
    required = {
        "Zone_Origin_Code", "Zone_Dest_Code", "DeadHead",
        "EoB", "RPM_Q2", "InRoute_TotalDistance", "Duration_Hours",
        "Cycle", "Start_Time",
    }
    df = pd.read_excel(path)
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"ERROR: columnas faltantes en el archivo: {missing}")
    return df


def build_tables(df: pd.DataFrame) -> tuple[dict, dict]:
    """Construye eob_table y rate_table desde lanes cargadas."""
    loaded = df[df["DeadHead"] == 0].copy()
    eob_table = (
        loaded.groupby(["Zone_Origin_Code", "Zone_Dest_Code"])["EoB"]
        .mean().dropna().to_dict()
    )
    rate_table = (
        loaded.groupby(["Zone_Origin_Code", "Zone_Dest_Code"])["RPM_Q2"]
        .mean().dropna().to_dict()
    )
    rate_table = {k: v for k, v in rate_table.items() if not np.isnan(v)}
    return eob_table, rate_table


def results_to_dataframe(results: list[dict]) -> pd.DataFrame:
    rows = []
    for cycle_id, res in enumerate(results, start=1):
        for seq, lane in enumerate(res["cycle"], start=1):
            rows.append({
                "Cycle_ID":        cycle_id,
                "Lane_Seq":        seq,
                "Lane":            lane["Lane"],
                "Zone_Origin":     lane["Zone_Origin"],
                "Zone_Dest":       lane["Zone_Dest"],
                "DeadHead":        lane["DeadHead"],
                "EoB":             lane["EoB"],
                "Distance_mi":     lane["Distance_mi"],
                "Duration_hrs":    lane["Duration_hrs"],
                "EoB_avg_cycle":   res["eob_avg"],
                "RPM_Q2_avg_cycle": res["rpm_avg"],
                "n_loaded":        res["n_loaded"],
                "n_deadhead":      res["n_dh"],
            })
    return pd.DataFrame(rows)


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generador de rutas por imitación (Markov v2)"
    )
    p.add_argument("--input",    default=DEFAULT_INPUT,   help="Archivo Excel de entrada")
    p.add_argument("--output",   default=DEFAULT_OUTPUT,  help="Archivo Excel de salida")
    p.add_argument("--n",        type=int,   default=DEFAULT_N,       help="Ciclos a generar")
    p.add_argument("--seed",     type=int,   default=DEFAULT_SEED,    help="Semilla aleatoria")
    p.add_argument("--min-eob",  type=float, default=DEFAULT_MIN_EOB, help="EoB mínimo por lane")
    p.add_argument("--n-loaded", type=int,   default=DEFAULT_N_LOADED,
                   help="Lanes cargadas por ciclo (default: aleatorio 3–4)")
    return p.parse_args()


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    np.random.seed(args.seed)

    print(f"Cargando datos desde '{args.input}'...")
    df = load_data(args.input)

    # Renombrar para compatibilidad interna
    df["Zone_Origin_Code"] = df["Zone_Origin_Code"].astype(str)
    df["Zone_Dest_Code"]   = df["Zone_Dest_Code"].astype(str)

    n_cycles = df["Cycle"].nunique()
    n_zones  = len(set(df["Zone_Origin_Code"]) | set(df["Zone_Dest_Code"]))
    print(f"  {len(df):,} lanes - {n_cycles:,} ciclos - {n_zones} zonas unicas")

    print("Construyendo tablas de EoB y RPM...")
    eob_table, rate_table = build_tables(df)
    global_p50 = float(np.median(list(rate_table.values()))) if rate_table else 0.0
    print(f"  RPM_Q2 p50 global = ${global_p50:.2f}/mi")

    print("Entrenando modelo...")
    model = RouteImitator()
    model.fit(df)

    print(f"Generando {args.n} ciclos aceptados (seed={args.seed}, EoB>={args.min_eob:.0f})...")
    results, attempts = model.generate_batch(
        eob_table  = eob_table,
        rate_table = rate_table,
        n          = args.n,
        min_eob    = args.min_eob,
        n_loaded   = args.n_loaded,
    )

    acceptance = len(results) / attempts * 100 if attempts else 0
    print(f"  {len(results)} aceptados de {attempts:,} intentos ({acceptance:.2f}%)")

    if not results:
        sys.exit("ERROR: no se generaron ciclos. Revisa el umbral EoB o los datos de entrada.")

    out_df = results_to_dataframe(results)
    out_path = Path(args.output)
    out_df.to_excel(out_path, index=False)
    print(f"Archivo guardado: {out_path.resolve()}")
    print(f"  {len(out_df):,} filas - {len(results)} ciclos - "
          f"EoB avg={out_df[out_df['DeadHead']==0]['EoB'].mean():.1f} - "
          f"RPM avg=${out_df[out_df['DeadHead']==0]['RPM_Q2_avg_cycle'].mean():.2f}")


if __name__ == "__main__":
    main()
