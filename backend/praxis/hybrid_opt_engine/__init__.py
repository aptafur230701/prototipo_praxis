"""
Hybrid Opt Engine -- motor de busqueda y optimizacion de rutas de Praxis.

Aqui viven las rutas propuestas que se consultan cuando el sistema recibe un
vector de estado y necesita sugerencias de rutas. El proceso que genera esas
rutas candidatas (Hunter Mode) esta fuera de alcance de este modulo: lo que
se expone es su output, en la ventana rodante de reportes diarios de
`data/hunter_mode/daily/<YYYY-MM-DD>/zones_rerouting_report.parquet`.

Submodulos:
  candidate_routes.py   consulta el pool de rutas candidatas de un dia dado,
                         ordenadas por una metrica simple (profit/mileage/...).
  scoring.py             selecciona "la mejor" candidata con el modelo real
                         HistGradientBoosting (scoring_policy_v2, Capa 2) --
                         get_best_route() reemplaza la seleccion por sort
                         simple de candidate_routes.py.
  v_final.py             V_final(zona, equipo, dia): shrinkage de Buhlmann
                         sobre la ventana rodante, usado por scoring.py.
  imitation/             generador por imitacion (Markov chain sobre hubs) que
                         aprende del comportamiento real de un carrier -- ver
                         imitation/__init__.py
"""
