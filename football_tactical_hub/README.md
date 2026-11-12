# ⚽ Football Tactical Data Hub

Hub multipágina en **Streamlit** para explorar equipos, jugadores y competiciones de varias fuentes de datos de fútbol, con **nombres normalizados** para poder cruzarlas.

## Páginas
- **Portada (hub)**: buscador global de equipos, KPIs del catálogo, accesos, últimos partidos y estado de las fuentes.
- **Competiciones**: todas las competiciones y temporadas (filtros por género, competición y temporada). Clasificación y partidos descargables.
- **Equipo**: historial completo (todas las competiciones y temporadas, y partidos de otras fuentes cruzados), agregados, plantilla y mapas.
- **Comparador de equipos**: dos equipos frente a frente con todas las fuentes cruzadas e historial de enfrentamientos directos.
- **Jugador**: partidos jugados, comparativa por 90 minutos y mapa agregado.
- **Análisis de partido**: mapas tácticos de un partido.
- **Vídeo (seguimiento)**: analiza el `tracks.parquet` del módulo `football-vision-analyzer` (repositorio aparte) (demo, subida o API): mapas de calor, distancia y velocidad por jugador, forma del equipo y posesión aproximada, y **cruce con los eventos de StatsBomb** (busca solo el desfase vídeo-eventos).
- **Fuentes de datos**: Understat, football-data.co.uk, football-data.org y API-Football, con esquema unificado, equivalencias de nombres y estado del almacén.

## Fuentes
| Fuente | Clave | Qué aporta |
|---|---|---|
| StatsBomb Open Data | No | Eventos completos (24 competiciones, ~4.000 partidos) |
| Understat (`soccerdata`) | No | xG por partido, jugadores por temporada, tiros |
| football-data.co.uk | No | Resultados y tiros/córners/tarjetas de 19 ligas (incl. Portugal) desde 1994/95 |
| football-data.org | `FOOTBALL_DATA_API_KEY` | 12 competiciones (10 peticiones/min) |
| API-Football | `API_FOOTBALL_KEY` | Miles de ligas (plan gratuito con tope diario) |

Las claves se guardan en **Streamlit Cloud → Settings → Secrets** (o como variables de entorno), nunca en el código:
```toml
FOOTBALL_DATA_API_KEY = "tu_token"
API_FOOTBALL_KEY = "tu_clave"
```

## Estructura
```
football_hub_v2/
├── app.py              # navegación + filtros globales del catálogo
├── core.py             # StatsBomb: catálogo, eventos, estadísticas
├── normalize.py        # normalización de nombres (alias propios en data/team_aliases.csv)
├── warehouse.py        # almacén Parquet de partidos normalizados
├── video_analysis.py   # métricas sobre los datos de seguimiento del vídeo
├── sources/            # un adaptador por fuente + esquema unificado
├── scripts/ingest.py   # ingesta de datos al almacén
├── data/               # almacén (warehouse/) y alias de equipos
├── tests/              # pruebas (pytest)
├── views/              # una página por archivo
└── requirements.txt
```

## Ingesta nocturna
`.github/workflows/ingest.yml` (en la **raíz** del repositorio) ejecuta cada día `scripts/ingest.py`, que descarga football-data.co.uk (19 ligas) y, si existe el secreto `FOOTBALL_DATA_API_KEY`, football-data.org, y guarda `data/warehouse/matches.parquet`. La primera vez, lánzala a mano en la pestaña **Actions → Ingesta de datos → Run workflow**. Cada actualización provoca un nuevo despliegue de la app. Para incluir Understat (xG), añade `--understat` al comando del workflow; es un scraper y puede fallar desde los servidores de GitHub sin romper la ingesta.

Alias a mano: `data/team_aliases.csv` y `data/player_aliases.csv` (columnas `alias,canonical`). La pestaña «Almacén» de Fuentes lista los equipos sin equivalencia que conviene añadir.

## Pruebas
```bash
pip install pytest && pytest
```

## Ejecución local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue
Streamlit Community Cloud → Main file path: `football_hub_v2/app.py`.

## Notas
- Las tandas de penaltis no cuentan en goles ni xG.
- Las fuentes distintas de StatsBomb se cargan bajo demanda y viven en la sesión; no hay base de datos persistente (ver hoja de ruta).
- Datos: [StatsBomb Open Data](https://github.com/statsbomb/open-data). Cita a StatsBomb si publicas análisis.
