"""
Generador por imitacion -- Capa de Hybrid Opt Engine.

Aprende de los ciclos reales de un carrier (backtracking) una cadena de
Markov sobre hubs: matriz de transicion P(B|A), distribucion de hub de
inicio, distancia/duracion promedio por par (A,B) y P(deadhead | A->B).
Con eso genera ciclos nuevos de 3-4 lanes cargadas que imitan la forma del
comportamiento real, y los filtra por factibilidad (ease_of_booking >= 50
por lane) y rentabilidad (rate/milla >= Q2 historico del lane).

No corre en vivo: se piensa como un proceso programado que, cada tanto,
vuelve a leer el backtracking mas reciente y regenera las rutas imitadas.

route_imitator.py implementa esta logica (clase RouteImitator: fit() aprende
las matrices de transicion loaded/deadhead, start_zones y p_dh_after del
historial; generate_batch() genera ciclos nuevos con rejection sampling
filtrando por EoB >= min_eob y RPM_Q2 >= p50 global). Por defecto lee de
`data/imitation/ciclos_con_separador_semana_rpm.xlsx` y escribe a
`data/imitation/rutas_imitadas_500.xlsx` -- correr con:
    python -m praxis.hybrid_opt_engine.imitation.route_imitator
(desde backend/, con el venv activado). El reemplazo periodico del archivo
de entrada por el backtracking mas reciente queda pendiente (tarea futura).
"""
