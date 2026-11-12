"""
Prueba rapida de ArtifactCache contra la BD local.
Requiere: docker compose up -d && python scripts/create_demo_model.py primero.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from praxis.artifact_cache import ArtifactCache  # noqa: E402
from praxis.db import get_connection  # noqa: E402


def main():
    cache = ArtifactCache(db_conn_factory=get_connection)

    # get() devuelve {"tipo", "status", "model"} -- no el modelo pelado --
    # para que quien lo consuma sepa tambien si es CHAMPION o CHALLENGER.
    entry = cache.get("scoring_policy_v1")
    if entry is None:
        print("No se encontro 'scoring_policy_v1' como CHAMPION/CHALLENGER. Corriste el seed?")
        return

    print("1ra llamada  -> status:", entry["status"], "| tipo de modelo:", type(entry["model"]).__name__)

    entry_again = cache.get("scoring_policy_v1")
    print("2da llamada  -> mismo objeto en memoria (sin BD/disco):", entry_again["model"] is entry["model"])

    missing = cache.get("no_existe")
    print("artifact_id inexistente -> ", missing)


if __name__ == "__main__":
    main()
