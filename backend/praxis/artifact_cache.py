import os
import tempfile
import threading
import time

import joblib
from psycopg2.extras import RealDictCursor

ACTIVE_STATUSES = ("CHAMPION", "CHALLENGER")


class ArtifactCache:
    """
    Mantiene en memoria los artefactos CHAMPION/CHALLENGER para que el
    modulo de recomendacion de rutas nunca tenga que tocar la BD ni S3
    al generar una sugerencia.

    get() es la unica funcion que llama el flujo de creacion de rutas.
    Internamente, a lo sumo cada `check_interval_seconds` hace una query
    liviana (_needs_refresh) para saber si algo cambio; solo si cambio
    algo paga el costo real de volver a descargar/deserializar (_reload).
    """

    def __init__(self, db_conn_factory, s3_client=None, check_interval_seconds=None):
        self._db_conn_factory = db_conn_factory
        self._s3_client_override = s3_client
        self._s3 = None  # se crea solo si de verdad hay que descargar de S3
        self._check_interval = check_interval_seconds or int(
            os.environ.get("ARTIFACT_CACHE_TTL_SECONDS", 30)
        )

        self._cache = {}
        self._last_change_seen = None
        self._next_check_at = 0.0
        self._lock = threading.Lock()

    def get(self, artifact_id: str):
        """Llamado cada vez que se va a generar una sugerencia de ruta."""
        now = time.monotonic()
        if now >= self._next_check_at:
            with self._lock:
                # otro hilo ya pudo haber refrescado mientras esperabamos el lock
                if now >= self._next_check_at:
                    if self._needs_refresh():
                        self._reload()
                    self._next_check_at = now + self._check_interval
        return self._cache.get(artifact_id)

    def _needs_refresh(self) -> bool:
        """Query liviana: solo compara timestamps, no trae parametros ni archivos."""
        conn = self._db_conn_factory()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(promoted_at), MAX(retired_at) FROM artifacts")
                max_promoted, max_retired = cur.fetchone()
        finally:
            conn.close()

        candidates = [t for t in (max_promoted, max_retired) if t is not None]
        last_change = max(candidates) if candidates else None

        if last_change is None:
            return False
        if self._last_change_seen is None or last_change > self._last_change_seen:
            self._last_change_seen = last_change
            return True
        return False

    def _reload(self):
        """Trae los artefactos activos y los deja listos en memoria."""
        conn = self._db_conn_factory()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT artifact_id, tipo, status, parametros, archivo_path
                    FROM artifacts
                    WHERE status IN %s
                    """,
                    (ACTIVE_STATUSES,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        new_cache = {}
        for row in rows:
            if row["archivo_path"]:
                model = self._load_file(row["archivo_path"])
            else:
                model = row["parametros"]

            new_cache[row["artifact_id"]] = {
                "tipo": row["tipo"],
                "status": row["status"],
                "model": model,
            }

        self._cache = new_cache

    def _load_file(self, archivo_path: str):
        """
        archivo_path puede ser una ruta local (desarrollo: s3://bucket/key
        nunca existio como tal, se guarda el .joblib en disco) o una URI
        real s3://bucket/key (produccion, con credenciales de AWS).
        """
        if archivo_path.startswith("s3://"):
            return self._load_from_s3(archivo_path)
        return joblib.load(archivo_path)

    def _load_from_s3(self, s3_uri: str):
        if self._s3 is None:
            self._s3 = self._s3_client_override or _default_s3_client()

        bucket, key = _parse_s3_uri(s3_uri)
        with tempfile.NamedTemporaryFile(suffix=".joblib") as tmp:
            self._s3.download_fileobj(bucket, key, tmp)
            tmp.flush()
            return joblib.load(tmp.name)


def get_champion_artifact_id(conn, tipo: str = "scoring_policy"):
    """Id del artifact que hoy esta tomando decisiones reales para `tipo`, o None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT artifact_id FROM artifacts WHERE tipo = %s AND status = 'CHAMPION' LIMIT 1",
            (tipo,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _parse_s3_uri(s3_uri: str):
    bucket, _, key = s3_uri[len("s3://"):].partition("/")
    return bucket, key


def _default_s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
    )
