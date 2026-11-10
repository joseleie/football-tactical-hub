import streamlit as st

from core import get_all_matches

st.set_page_config(page_title="Football Tactical Data Hub", page_icon="⚽", layout="wide")

# ---------- Catálogo completo de StatsBomb + filtros globales (por defecto: TODO) ----------
all_matches = get_all_matches()
st.session_state["matches_all"] = all_matches
st.session_state.setdefault("extra_matches", None)  # partidos de otras fuentes cargados en "Fuentes"

st.sidebar.header("🔎 Filtros del catálogo")
gender = st.sidebar.radio("Género", ["Todos", "Masculino", "Femenino"], horizontal=True, key="f_gender")
df = all_matches if gender == "Todos" else all_matches[all_matches["gender"] == gender]

comps = sorted(df["competition"].unique())
st.session_state["f_comp"] = [c for c in st.session_state.get("f_comp", []) if c in comps]
sel_c = st.sidebar.multiselect("Competición", comps, key="f_comp", placeholder="Todas las competiciones")
if sel_c:
    df = df[df["competition"].isin(sel_c)]

seasons = sorted(df["season"].unique(), reverse=True)
st.session_state["f_season"] = [s for s in st.session_state.get("f_season", []) if s in seasons]
sel_s = st.sidebar.multiselect("Temporada", seasons, key="f_season", placeholder="Todas las temporadas")
if sel_s:
    df = df[df["season"].isin(sel_s)]

st.session_state["matches"] = df.reset_index(drop=True)
st.sidebar.caption(f"{len(df):,} de {len(all_matches):,} partidos de StatsBomb en el filtro")
st.sidebar.divider()

pages = [
    st.Page("views/portada.py", title="Portada", icon="🏠", default=True),
    st.Page("views/competiciones.py", title="Competiciones", icon="🏆"),
    st.Page("views/equipo.py", title="Equipo", icon="🛡️"),
    st.Page("views/jugador.py", title="Jugador", icon="👤"),
    st.Page("views/partido.py", title="Análisis de partido", icon="🎯"),
    st.Page("views/fuentes.py", title="Fuentes de datos", icon="🔌"),
]
st.navigation(pages).run()
