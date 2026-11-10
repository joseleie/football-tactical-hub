# ⚽ Football Tactical Data Hub

Hub multipágina en **Streamlit** para explorar equipos, jugadores y competiciones de varias fuentes de datos de fútbol, con **nombres normalizados** para poder cruzarlas.

## Páginas
- **Portada (hub)**: buscador global de equipos, KPIs del catálogo, accesos, últimos partidos y estado de las fuentes.
- **Competiciones**: todas las competiciones y temporadas (filtros por género, competición y temporada). Clasificación y partidos descargables.
- **Equipo**: historial completo (todas las competiciones y temporadas, y partidos de otras fuentes cruzados), agregados, plantilla y mapas.
- **Jugador**: partidos jugados, comparativa por 90 minutos y mapa agregado.
- **Análisis de partido**: mapas tácticos de un partido.
- **Fuentes de datos**: Understat, football-data.co.uk, football-data.org y API-Football, con esquema unificado y tabla de equivalencias de nombres.

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
├── normalize.py        # normalización de nombres de equipos y jugadores
├── sources/            # un adaptador por fuente + esquema unificado
├── views/              # una página por archivo
└── requirements.txt
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
