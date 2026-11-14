# 🗺️ Hoja de ruta

## Estado actual (hecho)
- Hub en Streamlit: portada, competiciones, equipo, jugador, partido y fuentes.
- StatsBomb Open Data completo (24 competiciones, ~4.000 partidos) con estadísticas por equipo y jugador.
- Fuentes adicionales: Understat, football-data.co.uk, football-data.org y API-Football.
- Normalización de nombres de equipos y esquema unificado de partido.
- Portada con la temporada en curso (football-data.co.uk) y, si falla la descarga, desde el almacén.
- **Almacén propio en Parquet** con ingesta nocturna (GitHub Actions) y alias de equipos editables (`data/team_aliases.csv`).
- **Página «Vídeo (seguimiento)»**: lee `tracks.parquet` del módulo de vídeo (demo, subida o API) y calcula mapas de calor, distancia y velocidad por jugador, forma del equipo y posesión aproximada.
- **Módulo de vídeo `football-vision-analyzer`** (repositorio aparte): backend FastAPI + Celery, detector YOLO, ByteTrack, clasificador de equipos, homografía y frontend React. 32 pruebas con vídeo sintético.

---

## Fase 1 · Base de datos propia y cruce de fuentes
**Objetivo:** que los datos persistan, se actualicen solos y se crucen de forma fiable.

- [x] Capa de persistencia con **Parquet** (`warehouse.py`). DuckDB queda como mejora si las consultas crecen.
- [ ] Modelo de datos: `competition`, `team`, `team_alias`, `match`, `match_source_id`, `player`, `player_alias` y tablas de hechos (estadísticas por partido y por jugador).
- [x] **Ingesta programada** con GitHub Actions (cron nocturno): football-data.co.uk (19 ligas) y football-data.org. Pendiente: zona *raw* separada de la canónica.
- [x] Tabla de **alias editable a mano** para equipos (`data/team_aliases.csv`). Alias de jugadores en `data/player_aliases.csv`.
- [x] Cruce de partidos entre fuentes por fecha y claves normalizadas de equipo (duplicados eliminados en el historial y en el comparador). Tolera ± 1 día por husos horarios.
- [x] Informe de calidad en la pestaña «Almacén»: cobertura por fuente, errores de la última ingesta, partidos duplicados entre fuentes y equipos sin equivalencia (candidatos a alias).
- [~] Streamlit **lee** el almacén para los partidos de otras fuentes. Understat ya es opcional en la ingesta (`--understat`). Pendiente: API-Football y las tablas de jugador y de hechos.

## Fase 2 · Mejoras del hub
- [x] Gráficos de la portada ordenados de mayor a menor.
- [ ] Página de jugador con datos de Understat (xG/xA por temporada) cruzados por nombre normalizado.
- [x] Comparador de equipos entre fuentes, con historial de enfrentamientos directos. Pendiente: comparador de jugadores entre fuentes.
- [ ] Más ligas y competiciones de la temporada en curso (según fuentes gratuitas).
- [x] Pruebas automáticas (CI) en GitHub Actions para el hub (`tests.yml`) y para el analizador de vídeo (`ci.yml`, con la compilación del frontend).

---

- [x] **Estudio de Metrica Sports** y mapa de qué replicar con código abierto: `docs/ESTUDIO_METRICA.md`.
- [x] **Datos reales de Metrica** integrados en la página «Vídeo» (adaptador `metrica_data.py`), usados para validar con datos reales las métricas físicas y la sincronización vídeo-eventos.
- [x] **Análisis táctico sobre seguimiento**: control del espacio (Voronoi), altura de línea defensiva y compacidad, y fases de posesión.
- [x] **Medición de recursos**: `scripts/benchmark.py` y `docs/RECURSOS.md` en el analizador de vídeo.

## Fase 3 · Módulo de vídeo (`football-vision-analyzer`)
**Objetivo:** subir un vídeo de un partido (cámara táctica/cenital), detectar jugadores, balón y árbitros, seguirlos con un ID persistente, clasificar el equipo por el color de la camiseta y proyectar las posiciones sobre un plano 2D del campo (homografía).

### Decisión de arquitectura: proyecto separado
Este módulo **no puede vivir dentro de Streamlit Community Cloud**: no hay GPU, la memoria es limitada y no se pueden ejecutar workers ni Redis. Por eso es un servicio aparte, con su propio repositorio:

```
football-vision-analyzer/
├── docker-compose.yml        # API + Redis + worker
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI
│   │   ├── core/             # config.py, celery_app.py
│   │   ├── services/         # downloader, detector, tracker, classifier, homography
│   │   └── api/endpoints.py  # /upload, /process, /status/{id}
│   └── models/best.pt        # pesos YOLO entrenados para fútbol
└── frontend/                 # React + Vite + Tailwind + Canvas
```

**Flujo:** React → FastAPI → cola Celery (Redis) → worker con GPU → resultado en Parquet/JSON → el hub de Streamlit lo lee y lo dibuja con los mismos mapas de campo.

### Contrato de datos con el hub (a fijar primero)
Un archivo por partido procesado, con una fila por jugador y fotograma:
`video_id`, `frame`, `t_seconds`, `track_id`, `class` (jugador/portero/árbitro/balón), `team` (A/B/otros), `x_px`, `y_px`, `x_pitch`, `y_pitch`, `confidence`.

### Hitos
- [~] **V0 · Prueba de concepto con material real (herramientas listas; falta ejecutarlo con un clip y pesos reales)** (cuaderno en Colab, clip de 30 s propio): YOLO + ByteTrack (paquete `trackers`) con `supervision`. Medir calidad y velocidad antes de construir nada más.
- [x] **V1 · Servicios**: `detector.py`, `tracker.py`, `classifier.py` (K-Means sobre el color de la camiseta) y `homography.py`, con pruebas sobre un clip fijo.
- [x] **V2 · API y procesamiento asíncrono**: FastAPI + Celery + Redis + Docker Compose. Estados de tarea, reintentos y límites de tamaño y duración.
- [x] **V3 · Frontend**: `VideoUploader.jsx` y `TacticalCanvas.jsx` (reproductor con superposición de cajas, IDs y minimapa).
- [x] **V4 · Integración con el hub**: página «Vídeo» con mapas de calor, posiciones, rendimiento, forma y posesión, y pestaña «Eventos StatsBomb» que busca el desfase vídeo-eventos y los superpone. Pendiente: validarlo con vídeo real.
- [ ] **V5 · Producción**: alojamiento con GPU, limpieza de archivos temporales, registros y monitorización.


### Siguientes hitos del módulo de vídeo (derivados del estudio)
- [ ] **V0 real**: ejecutar `scripts.v0_spike` y `scripts.benchmark --model` con un clip de cámara táctica y pesos reales; guardar `quality.json` y `recursos.json`.
- [ ] **V6 · Evaluación objetiva** con *SoccerTrack v2* (cámara panorámica fija con verdad terreno): medir la calidad de identidades en 45 min, no solo en clips.
- [ ] **V7 · Calibración automática del campo** con puntos clave (modelo entrenado), para no depender de clics manuales.
- [ ] **V8 · Mejor clasificación de equipos** con embeddings (SigLIP + UMAP + K-Means) frente al color LAB actual.
- [x] **V9 · Corrección de IDs**: cosido automático de trayectorias (en el hub y como paso opcional del pipeline del analizador) e interfaz para unir, dividir, reetiquetar y eliminar, con deshacer. Validado con movimiento real de Metrica en un caso favorable; falta medirlo con detecciones reales.
- [ ] **V10 · Detección en panorámicas 4K** por mosaicos (los jugadores son pequeños).
- [ ] Dorsales y reidentificación (reto abierto).

### Riesgos y decisiones abiertas
- **Legal:** descargar vídeos de YouTube con `yt-dlp` suele ir contra los términos de servicio de YouTube salvo que tengas permiso del titular. La vía por defecto será **subir un archivo con derechos de uso**; la descarga por URL quedará como función opcional, desactivada por defecto y solo para contenido propio o con licencia.
- **Modelo:** `best.pt` hay que entrenarlo o conseguirlo con una licencia que permita su uso. Hay que verificar la licencia de los conjuntos de datos y de los pesos.
- **Homografía:** requiere puntos de referencia del campo (esquinas, áreas, círculo central). Con cámara fija es un cálculo único; con cámara móvil hay que estimarla por fotograma (modelo de puntos clave).
- **Coste de GPU y tiempos:** decidir si se procesan clips o partidos completos y dónde se aloja la GPU.
- **Memoria (VRAM):** procesar por lotes, reducir resolución y FPS cuando haga falta.
- **Derechos de imagen y datos personales:** revisar si el vídeo muestra personas identificables antes de publicarlo.

---

## Orden recomendado a partir de ahora
1. **Ejecutar V0** (`python -m scripts.v0_spike --video clip.mp4`): genera informe de calidad, vídeo anotado y estimación de tiempo de un partido completo. Es lo que decide la calidad del módulo de vídeo; todo lo demás está probado solo con vídeo sintético.
2. Completar Fase 1: API-Football en la ingesta, tablas de jugador y de hechos, y migrar a DuckDB si crece.
3. Fase 2 (comparadores, más ligas, CI) y validar el cruce vídeo-eventos con un partido real.
4. V5 (producción con GPU) cuando V0 confirme la viabilidad.
