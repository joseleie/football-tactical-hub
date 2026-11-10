import streamlit as st

from core import MAP_MODES, draw_pitch_map, extract_xy, load_scope

ctx = st.session_state["ctx"]
matches = st.session_state["matches"]

st.title("🎯 Análisis de un partido")
st.caption(ctx["label"])

labels = {
    int(r["match_id"]): f"{r['home_team']} {r['home_score']} - {r['away_score']} {r['away_team']} ({r['match_date']})"
    for _, r in matches.iterrows()
}
match_id = st.selectbox("Partido", list(labels.keys()), format_func=lambda k: labels[k], key="w_match")
row = matches[matches["match_id"] == match_id].iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("Local", row["home_team"], int(row["home_score"]), delta_color="off")
c2.metric("Visitante", row["away_team"], int(row["away_score"]), delta_color="off")
c3.metric("Fecha", str(row["match_date"]))

ev, _ = load_scope((int(match_id),))
if ev.empty:
    st.error("No se pudieron cargar los eventos del partido.")
    st.stop()

team = st.selectbox("Equipo a analizar", ev["team"].dropna().unique(), key="w_match_team")
tev = ev[ev["team"] == team]
players = st.multiselect("Jugador(es)", sorted(tev["player"].dropna().unique()), key="w_match_players")
types = sorted(tev["type"].dropna().unique())
sel_types = st.multiselect("Tipos de evento", types, default=[x for x in ["Pass", "Carry"] if x in types], key="w_match_types")
mode = st.radio("Representación", MAP_MODES, horizontal=True, key="w_match_mode")

f = tev
if players:
    f = f[f["player"].isin(players)]
if sel_types:
    f = f[f["type"].isin(sel_types)]
st.markdown(f"**{len(f)}** acciones que cumplen los filtros.")
draw_pitch_map(extract_xy(f), mode)

with st.expander("📊 Registros en bruto"):
    cols = [c for c in ["minute", "second", "type", "player", "position", "location"] if c in f.columns]
    st.dataframe(f[cols].head(200), width="stretch")
