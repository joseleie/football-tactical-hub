import pandas as pd
import streamlit as st

from core import get_competitions, load_scope, team_matches, teams_of
from normalize import norm_key

matches = st.session_state["matches"]
all_matches = st.session_state["matches_all"]
extra = st.session_state.get("extra_matches")

# ---------- Hero ----------
st.markdown("# ⚽ Football Tactical Data Hub")
st.markdown(
    "**Un único sitio para explorar equipos, jugadores y competiciones de varias fuentes de datos de fútbol**, "
    "con nombres normalizados para poder cruzarlas."
)

# ---------- Buscador global ----------
q = st.text_input("🔎 Busca un equipo", placeholder="Ej.: Barcelona, Croatia, Arsenal, Lyon…", key="home_search")
if q.strip():
    key = norm_key(q)
    pool = [all_matches[["home_team", "home_key", "competition", "season"]].rename(columns={"home_team": "team", "home_key": "k"}),
            all_matches[["away_team", "away_key", "competition", "season"]].rename(columns={"away_team": "team", "away_key": "k"})]
    pool = pd.concat(pool)
    hit = pool[pool["k"].str.contains(key, regex=False) | pool["team"].str.lower().str.contains(q.strip().lower(), regex=False)]
    if hit.empty:
        st.info("Sin resultados en StatsBomb. Prueba en «Fuentes de datos» para cargar otras fuentes.")
    else:
        res = (hit.groupby("team").agg(Partidos=("team", "size"), Competiciones=("competition", lambda s: ", ".join(sorted(set(s))[:3]))).reset_index()
               .sort_values("Partidos", ascending=False).head(20))
        st.caption("Pulsa una fila para seleccionar el equipo.")
        ev_sel = st.dataframe(res, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="home_results")
        if ev_sel.selection.rows:
            team = res.iloc[ev_sel.selection.rows[0]]["team"]
            st.session_state["team"], st.session_state["player"] = team, None
            b1, b2 = st.columns(2)
            if b1.button(f"🛡️ Abrir equipo: {team}", type="primary"):
                st.switch_page("views/equipo.py")
            if b2.button(f"👤 Ver jugadores de {team}"):
                st.switch_page("views/jugador.py")

# ---------- KPIs ----------
comps_cat = get_competitions()
k = st.columns(5)
k[0].metric("Competiciones", comps_cat["competition_name"].nunique())
k[1].metric("Temporadas (competición×año)", len(comps_cat.drop_duplicates(["competition_id", "season_id"])))
k[2].metric("Partidos con eventos", f"{len(all_matches):,}")
k[3].metric("Equipos", f"{len(teams_of(all_matches)):,}")
k[4].metric("Partidos de otras fuentes", "—" if extra is None else f"{len(extra):,}")

# ---------- Accesos ----------
st.subheader("Explora")
c = st.columns(5)
cards = [
    ("🏆 Competiciones", "Clasificaciones y todos los partidos de cada torneo y temporada.", "views/competiciones.py"),
    ("🛡️ Equipos", "Historial completo, agregados, plantilla y mapas.", "views/equipo.py"),
    ("👤 Jugadores", "Partidos jugados y comparativa por 90 minutos.", "views/jugador.py"),
    ("🎯 Partidos", "Mapas tácticos de un partido concreto.", "views/partido.py"),
    ("🔌 Fuentes", "Understat, football-data y más, normalizadas.", "views/fuentes.py"),
]
for col, (title, text, page) in zip(c, cards):
    with col.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(text)
        st.page_link(page, label="Abrir →")

# ---------- Últimos partidos y competiciones ----------
left, right = st.columns([3, 2])
with left:
    st.subheader("🕒 Últimos partidos del catálogo")
    last = matches.sort_values("match_date", ascending=False).head(12)
    st.dataframe(
        last.assign(Marcador=last["home_score"].astype("Int64").astype(str) + " - " + last["away_score"].astype("Int64").astype(str))
        [["match_date", "competition", "season", "home_team", "Marcador", "away_team"]]
        .rename(columns={"match_date": "Fecha", "competition": "Competición", "season": "Temporada", "home_team": "Local", "away_team": "Visitante"}),
        hide_index=True, width="stretch",
    )
with right:
    st.subheader("📚 Competiciones con más partidos")
    top = matches.groupby("competition").size().sort_values(ascending=False).head(10)
    st.bar_chart(top, horizontal=True, height=330)

# ---------- Estado de fuentes ----------
st.subheader("🔌 Fuentes conectadas")
from sources import apifootball, footballdata_org

status = pd.DataFrame(
    [
        ["StatsBomb Open Data", "Eventos completos (pases, tiros, presiones, xG)", "✅ Activa"],
        ["Understat", "xG por partido, tiros y estadísticas de jugador (5 grandes ligas)", "✅ Disponible"],
        ["football-data.co.uk", "Resultados, tiros, córners y tarjetas de 19 ligas (incluye Portugal)", "✅ Sin clave"],
        ["football-data.org", "12 competiciones, resultados y tablas", "✅ Con clave" if footballdata_org.get_token() else "🔑 Falta clave"],
        ["API-Football", "Miles de ligas (plan gratuito con tope diario)", "✅ Con clave" if apifootball.get_token() else "🔑 Falta clave"],
    ],
    columns=["Fuente", "Qué aporta", "Estado"],
)
st.dataframe(status, hide_index=True, width="stretch")
st.caption("Detalles, límites y cómo configurar las claves en «Fuentes de datos».")
