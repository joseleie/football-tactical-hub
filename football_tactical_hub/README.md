# ⚽ Football Tactical Data Hub (Pro Edition)

Plataforma avanzada de análisis táctico y visualización de datos abiertos de fútbol construida con **Python**, **Streamlit** y **mplsoccer**.

## 🚀 Características Principales
- **Conexión Directa a la API de StatsBomb:** Extracción automatizada de partidos, competiciones y eventos tácticos (pases, conducciones, presiones, tiros, recuperaciones).
- **Filtros Tácticos Avanzados:** Selección por equipo, filtrado multi-jugador y tipos de eventos específicos.
- **Visualización Espacial:** 
  - Mapa de Dispersión (Scattering) interactivo sobre terreno de juego reglamentario.
  - Mapa de Calor de Densidad Táctica (KDE) para identificar zonas de mayor actividad e influencia.
- **Inspección de Datos en Bruto:** Tablas interactivas integradas para auditar los dataframes de eventos.

---

## 🛠️ Requisitos de Instalación

Asegúrate de tener Python instalado y ejecuta los siguientes comandos en tu terminal:

```bash
git clone https://github.com/tu-usuario/football-tactical-hub.git
cd football-tactical-hub
pip install -r requirements.txt
```

---

## ▶️ Cómo Ejecutar la Aplicación

Inicia el servidor local de Streamlit ejecutando:

```bash
streamlit run app.py
```

Se abrirá automáticamente una ventana en tu navegador web con el entorno visual interactivo.

---

## 📦 Dependencias (`requirements.txt`)
- `streamlit`
- `pandas`
- `statsbombpy`
- `matplotlib`
- `mplsoccer`
