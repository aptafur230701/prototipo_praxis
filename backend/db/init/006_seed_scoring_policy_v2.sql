-- Praxis / Knowledge State - Capa 2: Artefactos
-- Modelo real HistGradientBoosting (Pipeline_Candidatas_HGB), entrenado sobre
-- las variables Bp, Ceff, Cpf, V. Entra como CANDIDATE: todavia no reemplaza
-- a scoring_policy_v1 (CHAMPION) -- la promocion a CHALLENGER/CHAMPION
-- depende de la evaluacion offline / simulador, pendiente por separado.

INSERT INTO artifacts (
    artifact_id,
    tipo,
    status,
    archivo_path,
    metricas,
    descripcion,
    entrenado_por
) VALUES (
    'scoring_policy_v2',
    'scoring_policy',
    'CANDIDATE',
    'data/models/scoring_policy_v2.joblib',
    '{"top1_loo": 0.3743169398907104, "top5_loo": 0.5573770491803278, "top10_loo": 0.680327868852459, "mrr_loo": 0.47602110505210377, "roc_auc_loo": 0.9743911542467154, "pr_auc_loo": 0.07320225629124338, "prevalencia": 0.000634096732669322}'::jsonb,
    'HistGradientBoostingClassifier entrenado sobre Bp, Ceff, Cpf, V (Pipeline_Candidatas_HGB / repositorio Pipeline_Nuevo_Modelo_Rutas).',
    'Pipeline_Candidatas_HGB'
)
ON CONFLICT (artifact_id) DO NOTHING;
