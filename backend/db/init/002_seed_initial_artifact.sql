-- Artefacto inicial: el modelo HistGradientBoosting ya existente, como champion de arranque.
-- En desarrollo local, archivo_path apunta a un archivo en disco (lo crea
-- scripts/create_demo_model.py). En produccion, cambiar este valor a una
-- URI real s3://bucket/key -- ArtifactCache detecta el prefijo "s3://" y
-- usa boto3 automaticamente en vez de leer disco.

INSERT INTO artifacts (
    artifact_id,
    tipo,
    status,
    archivo_path,
    descripcion,
    entrenado_por,
    promoted_at
) VALUES (
    'scoring_policy_v1',
    'scoring_policy',
    'CHAMPION',
    'data/models/scoring_policy_v1.joblib',
    'Modelo de puntuacion de rutas basado en margen, deadhead y posicionamiento de destino. Implementado como HistGradientBoosting.',
    'setup_inicial',
    NOW()
)
ON CONFLICT (artifact_id) DO NOTHING;

-- Abre su periodo de "campeon actual" en el historial.
INSERT INTO artifact_champion_history (artifact_id, fue_campeon_desde)
SELECT a.artifact_id, a.promoted_at
FROM artifacts a
WHERE a.artifact_id = 'scoring_policy_v1'
  AND NOT EXISTS (
      SELECT 1 FROM artifact_champion_history h WHERE h.artifact_id = a.artifact_id
  );
