import pandas as pd
import streamlit as st

from core import get_competitions, standings, teams_of
from normalize import norm_key
from sources import apifootball, footballdata_csv as fdc, footballdata_org

matches = st.session_state["matches"]
all_matches = st.session_state["matches_all"]

# ---------- Temporada en curso (se carga sola, sin clave) ----------
MAIN_DIVS = ["SP1", "E0", "I1", "D1", "F1", "P1"]
season_now = fdc.current_season()
if "current_df" not in st.session_state:
    with st.spinner(f"Cargando la temporada {season_now} (football-data.co.uk)…"):
        st.session_state["current_df"], st.session_state["current_err"] = fdc.load_current(MAIN_DIVS, season_now)
cur = st.session_state["current_df"]
if len(cur) and not st.session_state.get("current_added"):
    base = st.session_state.get("extra_matches")
    new = pd.concat([base, cur], ignore_index=True) if base is not None else cur
    st.session_state["extra_matches"] = new.drop_duplicates(subset=["source", "competition", "season", "match_id"], keep="last")
    st.session_state["current_added"] = True
extra = st.session_state.get("extra_matches")
from_warehouse = False
if cur.empty and extra is not None and len(extra):  # sin conexión con football-data.co.uk: datos del almacén
    cur = extra[extra["season"] == season_now].copy()
    from_warehouse = len(cur) > 0

# ---------- Hero ----------
st.markdown("# ⚽ Football Tactical Data Hub")
st.markdown(
    "**Un único sitio para explorar equipos, jugadores y competiciones de varias fuentes de datos de fútbol**, "
    "con nombres normalizados para poder cruzarlas."
)
newest = max([all_matches["match_date"].max()] + ([cur["match_date"].max()] if len(cur) else []))
st.caption(f"📅 Datos hasta el {newest} · temporada en curso: {season_now}")

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
k[4].metric(f"Partidos {season_now}", f"{len(cur):,}" if len(cur) else "—")

# ---------- Actualidad ----------
st.subheader(f"🔥 Actualidad · temporada {season_now}")
if cur.empty:
    st.info("No se pudo cargar la temporada en curso (el sitio no respondió). Puedes cargarla a mano en «Fuentes de datos → football-data.co.uk».")
else:
    a1, a2, a3 = st.columns(3)
    a1.metric("Partidos jugados", f"{len(cur):,}")
    a2.metric("Goles", int(cur["home_score"].sum() + cur["away_score"].sum()))
    a3.metric("Último partido", cur["match_date"].max())
    tabs_now = st.tabs(sorted(cur["competition"].unique()))
    for tab, lg in zip(tabs_now, sorted(cur["competition"].unique())):
        with tab:
            sub = cur[cur["competition"] == lg]
            l, r = st.columns([3, 2])
            l.dataframe(standings(sub), hide_index=True, width="stretch", height=360)
            last_ = sub.sort_values("match_date", ascending=False).head(10)
            r.dataframe(
                last_.assign(Marcador=last_["home_score"].astype("Int64").astype(str) + " - " + last_["away_score"].astype("Int64").astype(str))
                [["match_date", "home_team", "Marcador", "away_team"]]
                .rename(columns={"match_date": "Fecha", "home_team": "Local", "away_team": "Visitante"}),
                hide_index=True, width="stretch", height=360,
            )
if st.session_state.get("current_err"):
    st.caption("Sin datos de: " + ", ".join(st.session_state["current_err"]))
if from_warehouse:
    from warehouse import read_meta
    st.caption(f"Mostrando datos del almacén (última ingesta: {read_meta().get('updated_utc', 'desconocida')}) porque la descarga en vivo no respondió.")
st.caption(
    f"Fuente de la temporada en curso: football-data.co.uk (puede ir con algunos días de retraso). "
    f"StatsBomb Open Data llega hasta el {all_matches['match_date'].max()}; no publica partidos más recientes."
)

# ---------- Accesos ----------
st.subheader("Explora")
c = st.columns(6)
cards = [
    ("🏆 Competiciones", "Clasificaciones y todos los partidos de cada torneo y temporada.", "views/competiciones.py"),
    ("🛡️ Equipos", "Historial completo, agregados, plantilla y mapas.", "views/equipo.py"),
    ("👤 Jugadores", "Partidos jugados y comparativa por 90 minutos.", "views/jugador.py"),
    ("🎯 Partidos", "Mapas tácticos de un partido concreto.", "views/partido.py"),
    ("⚔️ Comparador", "Dos equipos frente a frente, con su historial directo.", "views/comparador.py"),
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
    st.subheader("🕒 Últimos partidos (todas las fuentes cargadas)")
    pool_recent = pd.concat([matches, extra], ignore_index=True) if extra is not None and len(extra) else matches
    last = pool_recent.sort_values("match_date", ascending=False).head(12)
    st.dataframe(
        last.assign(Marcador=last["home_score"].astype("Int64").astype(str) + " - " + last["away_score"].astype("Int64").astype(str))
        [["match_date", "source", "competition", "season", "home_team", "Marcador", "away_team"]]
        .rename(columns={"match_date": "Fecha", "source": "Fuente", "competition": "Competición", "season": "Temporada", "home_team": "Local", "away_team": "Visitante"}),
        hide_index=True, width="stretch",
    )
with right:
    st.subheader("📚 Competiciones con más partidos")
    import altair as alt

    top = matches.groupby("competition").size().sort_values(ascending=False).head(10).rename("partidos").reset_index()
    st.altair_chart(
        alt.Chart(top).mark_bar().encode(x=alt.X("partidos:Q", title="Partidos"), y=alt.Y("competition:N", sort="-x", title=None),
                                         tooltip=["competition", "partidos"]).properties(height=330),
        width="stretch",
    )

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
