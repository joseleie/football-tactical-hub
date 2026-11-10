import streamlit as st

from core import get_competitions, get_matches

st.set_page_config(page_title="Football Tactical Data Hub", page_icon="⚽", layout="wide")

# ---------- Filtros globales de competición (válidos para todas las páginas) ----------
comps = get_competitions()
st.sidebar.header("🏆 Competición")
country = st.sidebar.selectbox("País / Categoría", sorted(comps["country_name"].unique()), key="g_country")
c_df = comps[comps["country_name"] == country]
comp = st.sidebar.selectbox("Torneo", sorted(c_df["competition_name"].unique()), key="g_comp")
s_df = c_df[c_df["competition_name"] == comp].sort_values("season_name", ascending=False)
season = st.sidebar.selectbox("Temporada", s_df["season_name"].tolist(), key="g_season")
row = s_df[s_df["season_name"] == season].iloc[0]

new_ctx = {
    "comp_id": int(row["competition_id"]),
    "season_id": int(row["season_id"]),
    "label": f"{comp} · {season}",
}
if st.session_state.get("ctx") != new_ctx:
    # Al cambiar de competición se reinician las selecciones de equipo y jugador
    st.session_state["ctx"] = new_ctx
    st.session_state["team"] = None
    st.session_state["player"] = None
    st.session_state["roster_team"] = None
st.session_state["matches"] = get_matches(new_ctx["comp_id"], new_ctx["season_id"])

pages = [
    st.Page("views/portada.py", title="Portada", icon="🏠", default=True),
    st.Page("views/equipo.py", title="Equipo", icon="🛡️"),
    st.Page("views/jugador.py", title="Jugador", icon="👤"),
    st.Page("views/partido.py", title="Análisis de partido", icon="🎯"),
    st.Page("views/tiros.py", title="Tiros recientes", icon="🥅"),
]
st.navigation(pages).run()
