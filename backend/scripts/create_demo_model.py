"""
Entrena un HistGradientBoostingRegressor de juguete y lo guarda en disco,
en la ruta que quedo registrada en artifacts.archivo_path para
scoring_policy_v1 (data/models/scoring_policy_v1.joblib). Solo para tener
algo real que ArtifactCache pueda deserializar en desarrollo local.

Correr desde backend/: python scripts/create_demo_model.py
"""
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "scoring_policy_v1.joblib"


def main():
    rng = np.random.default_rng(42)
    x = rng.random((200, 4))
    y = 150 * x[:, 0] + 45 * x[:, 1] - 100 * x[:, 2] + rng.normal(0, 1, 200)
    model = HistGradientBoostingRegressor(max_iter=50).fit(x, y)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Modelo demo guardado en {MODEL_PATH}")


if __name__ == "__main__":
    main()
