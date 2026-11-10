import pandas as pd
import streamlit as st

from core import (
    COUNT_METRICS, MAP_MODES, draw_pitch_map, extract_xy, form_string, load_scope,
    player_match_stats, player_summary, select_team, team_match_stats, team_matches, teams_of,
)

ctx = st.session_state["ctx"]
matches = st.session_state["matches"]
ICON = {"V": "🟢 V", "E": "🟡 E", "D": "🔴 D"}

st.title("🛡️ Página de equipo")
st.caption(ctx["label"])

teams = teams_of(matches)
team = select_team(teams, key="w_team_equipo")
tm = team_matches(matches, team)
ids = tuple(int(i) for i in tm["match_id"])
ev, minutes = load_scope(ids)

if ev.empty:
    st.error("No se pudieron cargar los eventos de los partidos de este equipo.")
    st.stop()

tms = team_match_stats(ev)
mine = tms[tms["team"] == team].set_index("match_id")
opp = tms[tms["team"] != team].groupby("match_id")[["pases", "pases_ok", "tiros", "xg", "presiones", "recuperaciones"]].sum()

# ---------- Cabecera ----------
pj = len(tm)
v, e_, d = (tm["resultado"] == v for v in ("V", "E", "D"))
gf, gc = int(tm["gf"].sum()), int(tm["gc"].sum())
c = st.columns(6)
c[0].metric("Partidos", pj)
c[1].metric("V-E-D", f"{int(v.sum())}-{int(e_.sum())}-{int(d.sum())}")
c[2].metric("Goles (F/C)", f"{gf} / {gc}", delta=gf - gc)
c[3].metric("Puntos", int(tm["puntos"].sum()), delta=f"{tm['puntos'].mean():.2f} por partido", delta_color="off")
c[4].metric("xG a favor", f"{mine['xg'].sum():.1f}")
c[5].metric("xG en contra", f"{opp['xg'].sum():.1f}")
st.markdown(f"**Forma (últimos 5):** {form_string(tm['resultado'].tail(5))}")

tab_p, tab_a, tab_j, tab_m = st.tabs(["📅 Partidos", "📈 Agregados y comparativa", "👥 Jugadores", "🗺️ Mapa del equipo"])

# ---------- Partidos ----------
with tab_p:
    t = tm.copy()
    t["Resultado"] = t["resultado"].map(ICON)
    t["xG a favor"] = t["match_id"].map(mine["xg"]).round(2)
    t["xG en contra"] = t["match_id"].map(opp["xg"]).round(2)
    t["Tiros"] = t["match_id"].map(mine["tiros"]).astype("Int64")
    t["Pases"] = t["match_id"].map(mine["pases"]).astype("Int64")
    t["% pases"] = (t["match_id"].map(mine["pases_ok"]) / t["match_id"].map(mine["pases"]) * 100).round(1)
    show = t[["match_date", "rival", "condicion", "marcador", "Resultado", "xG a favor", "xG en contra", "Tiros", "Pases", "% pases"]]
    show.columns = ["Fecha", "Rival", "Condición", "Marcador", "Resultado", "xG a favor", "xG en contra", "Tiros", "Pases", "% pases"]
    st.dataframe(show, hide_index=True, width="stretch")

# ---------- Agregados ----------
with tab_a:
    st.markdown("#### Evolución por partido")
    evo = pd.DataFrame(
        {"xG a favor": tm["match_id"].map(mine["xg"]).values, "xG en contra": tm["match_id"].map(opp["xg"]).values},
        index=tm["match_date"].astype(str) + " vs " + tm["rival"],
    )
    st.line_chart(evo, height=300)

    st.markdown("#### Media por partido: a favor, en contra y frente a la competición")
    # Media de goles de toda la competición (por equipo y partido)
    league_gf = (matches["home_score"].fillna(0).sum() + matches["away_score"].fillna(0).sum()) / (2 * len(matches))
    rows = [
        ("Goles", gf / pj, gc / pj, league_gf),
        ("xG", mine["xg"].mean(), opp["xg"].mean(), None),
        ("Tiros", mine["tiros"].mean(), opp["tiros"].mean(), None),
        ("Pases", mine["pases"].mean(), opp["pases"].mean(), None),
        ("Presiones", mine["presiones"].mean(), opp["presiones"].mean(), None),
        ("Recuperaciones", mine["recuperaciones"].mean(), opp["recuperaciones"].mean(), None),
    ]
    comp = pd.DataFrame(rows, columns=["Métrica", "A favor", "En contra", "Media de la competición (goles)"]).round(2)
    st.dataframe(comp, hide_index=True, width="stretch")
    total_pases = mine["pases"].sum() + opp["pases"].sum()
    st.caption(f"Proxy de posesión (cuota de pases): {mine['pases'].sum() / total_pases * 100:.1f}%.")

    st.markdown("#### Local frente a visitante")
    split = tm.groupby("condicion").agg(
        Partidos=("match_id", "count"), Puntos=("puntos", "sum"), GF=("gf", "sum"), GC=("gc", "sum"),
    )
    split["Puntos por partido"] = (split["Puntos"] / split["Partidos"]).round(2)
    st.dataframe(split, width="stretch")

# ---------- Jugadores ----------
pm = player_match_stats(ev, minutes)
summary = player_summary(pm[pm["team"] == team])
with tab_j:
    cols = ["player", "partidos", "minutos", "goles", "xg", "asistencias", "pases", "pct_pases", "tiros", "presiones", "recuperaciones"]
    tbl = summary[cols].sort_values("minutos", ascending=False).copy()
    tbl["xg"] = tbl["xg"].round(2)
    tbl["pct_pases"] = tbl["pct_pases"].round(1)
    tbl["minutos"] = tbl["minutos"].round(0).astype(int)
    tbl.columns = ["Jugador", "PJ", "Min", "Goles", "xG", "Asist.", "Pases", "% pases", "Tiros", "Presiones", "Recup."]
    st.dataframe(tbl, hide_index=True, width="stretch")
    players = tbl["Jugador"].tolist()
    pc1, pc2 = st.columns([3, 1])
    pick = pc1.selectbox("Abrir la página de un jugador", players, key="pick_player_equipo")
    pc2.write("")
    if pc2.button("Ver jugador →", type="primary"):
        st.session_state["player"] = pick
        st.switch_page("views/jugador.py")

# ---------- Mapa ----------
with tab_m:
    team_ev = ev[ev["team"] == team]
    types = sorted(team_ev["type"].dropna().unique())
    defaults = [x for x in ["Pass", "Carry"] if x in types]
    m1, m2 = st.columns(2)
    sel_types = m1.multiselect("Tipos de evento", types, default=defaults, key="map_types_equipo")
    mode = m2.radio("Representación", MAP_MODES, horizontal=True, key="map_mode_equipo")
    labels = {int(r.match_id): f"{r.match_date} vs {r.rival}" for r in tm.itertuples()}
    sel_matches = st.multiselect("Partidos (vacío = todos)", list(labels.keys()), format_func=lambda k: labels[k], key="map_matches_equipo")
    f = team_ev
    if sel_types:
        f = f[f["type"].isin(sel_types)]
    if sel_matches:
        f = f[f["match_id"].isin(sel_matches)]
    st.markdown(f"**{len(f)}** acciones agregadas de {len(sel_matches) or pj} partido(s).")
    draw_pitch_map(extract_xy(f), mode)
