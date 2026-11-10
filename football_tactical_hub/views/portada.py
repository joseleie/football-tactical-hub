import streamlit as st

from core import load_scope, player_match_stats, standings, team_matches, teams_of, select_team

ctx = st.session_state["ctx"]
matches = st.session_state["matches"]

st.title("⚽ Football Tactical Data Hub")
st.caption(f"Datos abiertos de StatsBomb · {ctx['label']}")

if matches.empty:
    st.warning("No hay partidos para esta competición.")
    st.stop()

# ---------- KPIs de la competición ----------
goals = float(matches["home_score"].fillna(0).sum() + matches["away_score"].fillna(0).sum())
k1, k2, k3, k4 = st.columns(4)
k1.metric("Partidos", len(matches))
k2.metric("Equipos", len(teams_of(matches)))
k3.metric("Goles", int(goals))
k4.metric("Goles por partido", f"{goals / len(matches):.2f}")

# ---------- Buscador ----------
st.subheader("🔎 Buscar equipo o jugador")
teams = teams_of(matches)
left, right = st.columns(2)

with left:
    team = select_team(teams, key="w_team_portada")
    if st.button("Ver página del equipo →", type="primary"):
        st.switch_page("views/equipo.py")

with right:
    st.markdown("**Jugadores del equipo**")
    if st.session_state.get("roster_team") != team:
        if st.button(f"Cargar plantilla de {team}"):
            st.session_state["roster_team"] = team
            st.rerun()
    else:
        tm = team_matches(matches, team)
        ev, minutes = load_scope(tuple(int(i) for i in tm["match_id"]))
        players = sorted(minutes[(minutes["team"] == team) & (minutes["minutos"] > 0)]["player"].unique())
        if players:
            cur = st.session_state.get("player")
            idx = players.index(cur) if cur in players else 0
            sel = st.selectbox("Jugador", players, index=idx, key="w_player_portada")
            st.session_state["player"] = sel
            if st.button("Ver página del jugador →", type="primary"):
                st.switch_page("views/jugador.py")
        else:
            st.info("No se encontraron jugadores.")

# ---------- Clasificación ----------
st.subheader("📊 Clasificación (acumulado de la competición)")
table = standings(matches)
st.caption("Pulsa una fila para seleccionar ese equipo y luego usa «Ver página del equipo».")
event = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row")
if event.selection.rows:
    picked = table.iloc[event.selection.rows[0]]["Equipo"]
    if picked != st.session_state.get("team"):
        st.session_state["team"] = picked
        st.session_state["player"] = None
        st.session_state["roster_team"] = None
        st.rerun()

st.subheader("⚔️ Goles a favor y en contra")
chart_df = table.set_index("Equipo")[["GF", "GC"]]
st.bar_chart(chart_df, height=360)

st.divider()
st.markdown(
    "**Cómo se usa:** elige un equipo para ver su página de agregados (todos sus partidos, plantilla y mapas) "
    "o carga su plantilla y abre la página de un jugador (todos los partidos donde jugó y su comparativa)."
)
