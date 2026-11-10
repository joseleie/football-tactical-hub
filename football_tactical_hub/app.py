import streamlit as st
import pandas as pd
from statsbombpy import sb
import matplotlib.pyplot as plt
from mplsoccer import Pitch

# Configuración de la página del Mini Site
st.set_page_config(page_title="Football Tactical Data Hub - Pro", page_icon="⚽", layout="wide")

st.title("⚽ Tactical Data Analyzer Hub (Pro Edition)")
st.markdown("Plataforma avanzada de análisis táctico con filtrado por jugador y mapas de calor espaciales (Datos abiertos de StatsBomb).")

@st.cache_data
def get_competitions():
    return sb.competitions()

comps_df = get_competitions()

# Barra lateral: Configuración de Competición
st.sidebar.header("1. Competición y Torneo")
country_list = comps_df['country_name'].unique()
selected_country = st.sidebar.selectbox("Selecciona País / Categoría", country_list)

filtered_comps = comps_df[comps_df['country_name'] == selected_country]
competition_name = st.sidebar.selectbox("Selecciona Torneo", filtered_comps['competition_name'].unique())

comp_row = filtered_comps[filtered_comps['competition_name'] == competition_name].iloc[0]
comp_id = comp_row['competition_id']
season_id = comp_row['season_id']

@st.cache_data
def get_matches(c_id, s_id):
    return sb.matches(competition_id=c_id, season_id=s_id)

matches_df = get_matches(comp_id, season_id)

st.sidebar.header("2. Selección de Partido")
match_options = matches_df.apply(lambda x: f"{x['home_team']} {x['home_score']} - {x['away_score']} {x['away_team']} ({x['match_date']})", axis=1)
selected_match_label = st.sidebar.selectbox("Selecciona el Partido", match_options)

selected_match_row = matches_df[match_options == selected_match_label].iloc[0]
match_id = selected_match_row['match_id']

# Cabecera con marcador
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Equipo Local", selected_match_row['home_team'], selected_match_row['home_score'])
with col2:
    st.metric("Equipo Visitante", selected_match_row['away_team'], selected_match_row['away_score'])
with col3:
    st.metric("Fecha del Encuentro", str(selected_match_row['match_date']))

@st.cache_data
def get_match_events(m_id):
    return sb.events(match_id=m_id)

with st.spinner("Conectando con la API y extrayendo eventos del partido..."):
    events_df = get_match_events(match_id)

# --- FILTROS TÁCTICOS AVANZADOS EN BARRA LATERAL ---
st.sidebar.header("3. Filtros Tácticos Avanzados")
team_options = events_df['team'].dropna().unique()
selected_team = st.sidebar.selectbox("Equipo a Analizar", team_options)

# Filtrar jugadores del equipo seleccionado
team_events = events_df[events_df['team'] == selected_team]
player_options = sorted(team_events['player'].dropna().unique())
selected_players = st.sidebar.multiselect("Filtrar por Jugador(es)", player_options, default=[])

event_types = sorted(team_events['type'].dropna().unique())
selected_events = st.sidebar.multiselect("Tipos de Evento Táctico", event_types, default=['Pass', 'Carry'])

# Aplicar filtros al DataFrame
filtered_events = team_events.copy()
if selected_players:
    filtered_events = filtered_events[filtered_events['player'].isin(selected_players)]
if selected_events:
    filtered_events = filtered_events[filtered_events['type'].isin(selected_events)]

st.subheader(f"🎯 Análisis Espacial: {selected_team}")
st.markdown(f"Se han aislado **{len(filtered_events)}** acciones que cumplen con los filtros seleccionados.")

if len(filtered_events) > 0 and 'location' in filtered_events.columns:
    # Selector de tipo de visualización
    viz_mode = st.radio("Selecciona el tipo de representación táctica:", ["Mapa de Dispersión (Acciones)", "Mapa de Calor / Densidad (KDE)"], horizontal=True)

    pitch = Pitch(pitch_type='statsbomb', pitch_color='grass', line_color='white', line_zorder=2)
    fig, ax = pitch.draw(figsize=(10, 7))

    # Extraer coordenadas válidas [X, Y]
    valid_locs = filtered_events['location'].dropna()
    x_coords = valid_locs.apply(lambda loc: loc[0] if isinstance(loc, list) and len(loc) >= 2 else None)
    y_coords = valid_locs.apply(lambda loc: loc[1] if isinstance(loc, list) and len(loc) >= 2 else None)
    
    plot_df = pd.DataFrame({
        'x': x_coords, 
        'y': y_coords, 
        'type': filtered_events['type'], 
        'player': filtered_events['player']
    }).dropna()

    if len(plot_df) > 5:
        if viz_mode == "Mapa de Dispersión (Acciones)":
            event_colors = {'Pass': 'yellow', 'Carry': 'cyan', 'Pressure': 'orange', 'Shot': 'red', 'Ball Recovery': 'lime'}
            for ev_type, color in event_colors.items():
                subset = plot_df[plot_df['type'] == ev_type]
                if not subset.empty:
                    pitch.scatter(subset['x'], subset['y'], ax=ax, color=color, edgecolors='black', s=90, alpha=0.85, label=ev_type, zorder=3)
            ax.legend(loc='upper right', facecolor='black', edgecolor='white', labelcolor='white')
        else:
            # Mapa de calor de densidad táctica (KDE)
            try:
                pitch.kdeplot(plot_df['x'], plot_df['y'], ax=ax, cmap='hot', levels=100, fill=True, alpha=0.65, zorder=3)
                pitch.scatter(plot_df['x'], plot_df['y'], ax=ax, color='white', s=15, alpha=0.3, zorder=4)
            except Exception:
                st.warning("La densidad de puntos es muy baja para este filtro. Mostrando dispersión alternativa.")
                pitch.scatter(plot_df['x'], plot_df['y'], ax=ax, color='yellow', s=70, alpha=0.8, zorder=3)
    else:
        st.info("No hay suficientes coordenadas espaciales registradas para este filtro.")

    st.pyplot(fig)
else:
    st.info("No hay coordenadas espaciales disponibles en la API para esta combinación de filtros.")

# Tabla interactiva inferior con los datos filtrados
with st.expander("📊 Inspeccionar registros en bruto del DataFrame"):
    st.dataframe(filtered_events[['minute', 'second', 'type', 'player', 'position', 'location']].head(200), use_container_width=True)
