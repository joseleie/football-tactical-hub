# ⚽ Football Tactical Data Hub

App multipágina en **Streamlit** con datos abiertos de **StatsBomb** (y tiros recientes de Understat).

## Páginas
- **Portada**: KPIs de la competición, buscador de equipo y jugador, clasificación y goles a favor/en contra.
- **Equipo**: todos sus partidos, agregados y comparativa (local/visitante, a favor/en contra), tabla de jugadores y mapa agregado.
- **Jugador**: todos los partidos donde jugó, evolución, comparativa por 90 minutos (con compañeros u otro jugador) y mapa agregado.
- **Análisis de partido**: mapas tácticos de un partido concreto.
- **Tiros recientes**: tiros y xG de grandes ligas (Understat).

## Estructura
```
football_tactical_hub/
├── app.py            # navegación + filtros globales de competición
├── core.py           # carga de datos y estadísticas
├── views/            # una página por archivo
├── requirements.txt
└── .streamlit/config.toml
```

## Ejecución local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue (Streamlit Community Cloud)
Main file path: `football_tactical_hub/app.py` (o `app.py` si está en la raíz del repositorio).

## Notas
- La primera carga de un equipo descarga todos sus partidos (unos segundos); después queda en caché.
- Las tandas de penaltis no cuentan en goles ni xG.
- Datos: [StatsBomb Open Data](https://github.com/statsbomb/open-data). Cita a StatsBomb si publicas análisis.
