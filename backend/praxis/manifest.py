"""
Capa 4 -- Gobernanza y Manifiesto.

`production_manifest` es el tablero de control activo: un unico registro por
ambiente que dice cual artifact es CHAMPION (toma decisiones reales) y cual es
CHALLENGER (se evalua en paralelo, sin recibir trafico real). El historial de
quien fue champion vive en `artifact_champion_history` (Capa 2).

`promote_challenger()` -- mover el challenger a champion y retirar el
anterior -- queda para una tarea futura, una vez el simulador de evaluacion
este listo.
"""


def register_challenger(conn, artifact_id: str, ambiente: str = "produccion") -> None:
    """Registra `artifact_id` como challenger en evaluacion para `ambiente`."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE production_manifest
            SET challenger_id    = %s,
                challenger_desde = NOW(),
                updated_at       = NOW()
            WHERE ambiente = %s
            """,
            (artifact_id, ambiente),
        )
    conn.commit()
