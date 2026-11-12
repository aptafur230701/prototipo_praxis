# Praxis -- Knowledge State

Backend de Praxis: Capa 1 (Decision Ledger -- registra el contexto de cada
ruta creada), Capa 2 (Artefactos -- versiona y sirve en caliente los modelos
y politicas de scoring que usa la recomendacion de rutas) y Capa 4
(Gobernanza y Manifiesto -- el tablero de control que dice cual artifact
esta tomando decisiones reales hoy).

## Estructura

```
backend/
  docker-compose.yml       Postgres para desarrollo
  db/init/                 SQL que crea las tablas y siembra el artifact inicial
  praxis/
    db.py                  conexion a Postgres
    artifact_cache.py       ArtifactCache: carga en caliente, sin BD/S3 por request
    decision_ledger.py       build_vector_estado() + save_decision_record() (Capa 1)
    mock_context.py          fuentes aun no integradas (ELD, Samsara, mercado) -- TODOs
    zones.py                  resuelve un destino de texto al zone_id mas cercano
    manifest.py                register_challenger() (Capa 4 -- Gobernanza)
    api.py                    endpoint HTTP que conecta el formulario del frontend
  scripts/
    create_demo_model.py    entrena y guarda en disco un modelo de juguete (solo dev)
    smoke_test.py            prueba manual del cache
  data/
    models/                  generado localmente, no se sube a git (modelo de juguete)
    reference/                SI se sube a git -- catalogos reales (ej. zones_id.xlsx)
```

## Arranque local

```bash
cd backend
cp .env.example .env
docker compose up -d          # levanta Postgres (con las tablas + seed ya aplicados)
pip install -r requirements.txt

python scripts/create_demo_model.py   # guarda un .joblib de prueba en data/models/
python scripts/smoke_test.py          # valida que ArtifactCache lo carga y lo cachea
```

Todo corre con `backend/` como carpeta actual (los paths relativos de
`archivo_path` en la BD se resuelven contra ahi).

> Nota: en desarrollo no se simula S3 con Docker (MinIO/LocalStack dejaron de
> ofrecer imagenes gratis de forma confiable). `archivo_path` apunta a un
> archivo en disco; `ArtifactCache` lo lee directo con `joblib.load`. En
> produccion, poner ahi una URI real `s3://bucket/key` -- el mismo codigo
> detecta el prefijo y usa `boto3` con las credenciales de AWS del entorno.

La primera vez que se crea el volumen de Postgres, todos los `.sql` en
`db/init/` corren en orden: primero crean `artifacts` y
`artifact_champion_history`, despues insertan `scoring_policy_v1` como
`CHAMPION` y abren su periodo en el historial. Si cambias el esquema despues,
agrega un nuevo archivo `00N_*.sql` ahi -- no se re-ejecutan sobre un volumen
ya existente (bajar el volumen con `docker compose down -v` si quieres reiniciar).

## Que hace `ArtifactCache`

- `get(artifact_id)` es lo unico que llama el flujo de creacion de rutas.
- Cada `ARTIFACT_CACHE_TTL_SECONDS` (default 30s) hace como mucho una query
  liviana (`MAX(promoted_at)`, `MAX(retired_at)`) para saber si algo cambio.
- Solo si algo cambio, recarga de verdad: trae los artifacts `CHAMPION` y
  `CHALLENGER`, y por cada uno descarga+deserializa su `.joblib` de S3 (si
  usa `archivo_path`) o toma `parametros` directo (si los pesos caben en JSON).
- Ninguna de las dos rutas corre en el hilo de una solicitud de ruta real.

## Que hace `api.py` (Capa 1 -- Decision Ledger)

- `POST /decisions` es lo que llama el boton "Continue" del modal "Create
  route" en el frontend (`src/engine.js`), con CORS habilitado para el dev
  server de Vite (`localhost:5173`).
- Arma el vector de estado con `build_vector_estado()` juntando: el momento
  actual (`temporal`), el truck/driver (`mock_context.get_truck_context`,
  **mock** -- pendiente ELD real), HOS (`mock_context.get_hos_context`,
  **mock** -- pendiente Samsara `GET /hos/clocks`), mercado (**mock**, la
  fuente real todavia no esta definida), y lo que lleno el usuario en el
  formulario (`restricciones_y_objetivos`).
- `destino_final_code` SI es real: `zones.resolve_zone_code()` geocodifica el
  texto del destino con Nominatim (OpenStreetMap, gratis) y busca la zona mas
  cercana por distancia haversine contra `data/reference/zones_id.xlsx` (88
  zonas). Para volumen de produccion, Nominatim pide maximo 1 req/seg --
  si esto se usa mucho, cambiar a un geocoder de pago o self-hosteado.
- `millas_minimas_ruta` queda en `null` a proposito -- el formulario todavia
  no tiene ese campo.
- `politica_de_decision` se llena solo, con el artifact `CHAMPION` actual
  (`get_champion_artifact_id`) -- conecta el registro con la Capa 2.

Correr con `uvicorn praxis.api:app --reload --port 8000` desde `backend/`.

## Que hace `production_manifest` (Capa 4 -- Gobernanza y Manifiesto)

- Un unico registro por `ambiente` (hoy solo `'produccion'`, forzado con un
  indice `UNIQUE` sobre esa columna) -- no es historial, es el estado
  presente: quien es `champion_id` (toma decisiones reales ahora mismo) y
  quien es `challenger_id` (se esta evaluando en paralelo, o `NULL` si no hay
  ninguno en evaluacion).
- El historial de quien fue champion en el pasado sigue viviendo en
  `artifact_champion_history` (Capa 2) -- esta tabla no lo duplica.
- El challenger **no recibe trafico real**: sus predicciones se comparan
  contra el champion mediante un simulador que todavia esta en construccion.
- `manifest.register_challenger(conn, artifact_id)` es la unica funcion de
  esta capa por ahora: marca un artifact como challenger en evaluacion.
  `promote_challenger()` -- mover el challenger a champion y retirar el
  anterior -- queda para cuando el simulador y su criterio de decision esten
  definidos.

## Fuera de alcance (a proposito)

Promover un artifact a `CHAMPION` o retirarlo (cerrar su fila abierta en
`artifact_champion_history`, mover el anterior a `RETIRED`) no esta
implementado todavia -- esta tarea cubre inventario + registro inicial +
cache de lectura. Esa logica de transicion de estados es un siguiente paso
natural (como funcion de servicio o trigger), pero escribirla ahora sin un
caso de uso concreto (quien promueve, bajo que criterio) seria adivinar.
