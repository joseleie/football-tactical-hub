import pandas as pd
import streamlit as st

from core import (
    MAP_MODES, draw_pitch_map, extract_xy, form_string, player_match_stats, player_summary, scope_selector,
    select_team, team_counts, team_match_stats, team_matches, team_matches_by_key, teams_of,
)
from normalize import norm_key

matches = st.session_state["matches"]
all_matches = st.session_state["matches_all"]
extra = st.session_state.get("extra_matches")
ICON = {"V": "🟢 V", "E": "🟡 E", "D": "🔴 D"}
PRIORITY = {"StatsBomb": 0, "Understat": 1, "football-data.org": 2, "API-Football": 3, "football-data.co.uk": 4}

st.title("🛡️ Página de equipo")

teams = teams_of(matches)
cur = st.session_state.get("team")
if cur and cur not in teams:
    teams = sorted(teams + [cur])
counts = team_counts(all_matches)
team = select_team(teams, key="w_team_equipo", counts=counts)

base = matches if team in set(teams_of(matches)) else all_matches
tm_all = team_matches(base, team)
if tm_all.empty:
    st.info("Este equipo no tiene partidos con resultado en el catálogo.")
    st.stop()

scope_box = st.container()
tab_h, tab_a, tab_j, tab_m = st.tabs(["📚 Historial (todos los partidos)", "📈 Agregados y comparativa", "👥 Jugadores", "🗺️ Mapa del equipo"])


def summarize(t: pd.DataFrame) -> pd.DataFrame:
    g = t.groupby(["source", "competition", "season"])
    out = g.agg(PJ=("match_id", "size"), V=("resultado", lambda s: (s == "V").sum()), E=("resultado", lambda s: (s == "E").sum()),
                D=("resultado", lambda s: (s == "D").sum()), GF=("gf", "sum"), GC=("gc", "sum"), Pts=("puntos", "sum")).reset_index()
    out.columns = ["Fuente", "Competición", "Temporada", "PJ", "V", "E", "D", "GF", "GC", "Pts"]
    return out.sort_values("Temporada", ascending=False)


# ---------- Historial: no necesita cargar eventos ----------
with tab_h:
    hist = tm_all
    if extra is not None and len(extra):
        tm_ex = team_matches_by_key(extra, norm_key(team))
        if len(tm_ex):
            hist = pd.concat([tm_all, tm_ex], ignore_index=True)
            hist["_k"] = hist["rival"].map(norm_key)
            hist["_p"] = hist["source"].map(PRIORITY).fillna(9)
            before = len(hist)
            hist = hist.sort_values(["match_date", "_p"]).drop_duplicates(["match_date", "_k", "condicion"], keep="first").drop(columns=["_k", "_p"])
            st.caption(
                f"Incluye partidos de otras fuentes cargadas en «Fuentes de datos», cruzados por nombre normalizado. "
                f"Se descartaron {before - len(hist)} duplicados (mismo día, rival y condición; prioridad StatsBomb > Understat > football-data.org > API-Football > football-data.co.uk)."
            )
    c = st.columns(6)
    c[0].metric("Partidos", len(hist))
    c[1].metric("V-E-D", f"{(hist['resultado'] == 'V').sum()}-{(hist['resultado'] == 'E').sum()}-{(hist['resultado'] == 'D').sum()}")
    c[2].metric("Goles (F/C)", f"{int(hist['gf'].sum())} / {int(hist['gc'].sum())}")
    c[3].metric("Puntos", int(hist["puntos"].sum()))
    c[4].metric("Competiciones", hist["competition"].nunique())
    c[5].metric("Temporadas", hist["season"].nunique())
    st.markdown("#### Resumen por competición y temporada")
    st.dataframe(summarize(hist), hide_index=True, width="stretch")
    st.markdown("#### Todos los partidos")
    t = hist.copy()
    t["Resultado"] = t["resultado"].map(ICON)
    show = t[["match_date", "source", "competition", "season", "rival", "condicion", "marcador", "Resultado"]]
    show.columns = ["Fecha", "Fuente", "Competición", "Temporada", "Rival", "Condición", "Marcador", "Resultado"]
    st.dataframe(show.sort_values("Fecha", ascending=False), hide_index=True, width="stretch")

# ---------- Estadísticas detalladas (eventos) ----------
with scope_box:
    st.markdown("### 🔬 Estadísticas detalladas (eventos de StatsBomb)")
    if (tm_all["source"] == "StatsBomb").sum() == 0:
        st.info("Este equipo solo tiene partidos de otras fuentes, sin eventos detallados.")
        st.stop()
    tm, ev, minutes = scope_selector(tm_all, key=f"scope_equipo_{team}")

if ev.empty:
    st.error("No se pudieron cargar los eventos de estos partidos.")
    st.stop()

tms = team_match_stats(ev)
mine = tms[tms["team"] == team].set_index("match_id")
opp = tms[tms["team"] != team].groupby("match_id")[["pases", "pases_ok", "tiros", "xg", "presiones", "recuperaciones"]].sum()
pj = len(tm)
gf, gc = int(tm["gf"].sum()), int(tm["gc"].sum())

with scope_box:
    c = st.columns(6)
    c[0].metric("Partidos (ámbito)", pj)
    c[1].metric("V-E-D", f"{(tm['resultado'] == 'V').sum()}-{(tm['resultado'] == 'E').sum()}-{(tm['resultado'] == 'D').sum()}")
    c[2].metric("Goles (F/C)", f"{gf} / {gc}", delta=gf - gc)
    c[3].metric("Puntos", int(tm["puntos"].sum()), delta=f"{tm['puntos'].mean():.2f} por partido", delta_color="off")
    c[4].metric("xG a favor", f"{mine['xg'].sum():.1f}")
    c[5].metric("xG en contra", f"{opp['xg'].sum():.1f}")
    st.markdown(f"**Forma (últimos 5):** {form_string(tm['resultado'].tail(5))}")

with tab_a:
    st.markdown("#### Evolución por partido")
    evo = pd.DataFrame(
        {"xG a favor": tm["match_id"].map(mine["xg"]).values, "xG en contra": tm["match_id"].map(opp["xg"]).values},
        index=tm["match_date"].astype(str) + " vs " + tm["rival"],
    )
    st.line_chart(evo, height=300)
    st.markdown("#### Media por partido: a favor, en contra y frente a la competición")
    scope_matches = all_matches[all_matches["match_id"].isin(tm["match_id"])]
    league_gf = (scope_matches["home_score"].fillna(0).sum() + scope_matches["away_score"].fillna(0).sum()) / (2 * max(len(scope_matches), 1))
    rows = [
        ("Goles", gf / pj, gc / pj, league_gf),
        ("xG", mine["xg"].mean(), opp["xg"].mean(), None),
        ("Tiros", mine["tiros"].mean(), opp["tiros"].mean(), None),
        ("Pases", mine["pases"].mean(), opp["pases"].mean(), None),
        ("Presiones", mine["presiones"].mean(), opp["presiones"].mean(), None),
        ("Recuperaciones", mine["recuperaciones"].mean(), opp["recuperaciones"].mean(), None),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Métrica", "A favor", "En contra", "Media de los partidos del ámbito (goles)"]).round(2), hide_index=True, width="stretch")
    total_pases = mine["pases"].sum() + opp["pases"].sum()
    st.caption(f"Proxy de posesión (cuota de pases): {mine['pases'].sum() / total_pases * 100:.1f}%.")
    st.markdown("#### Local frente a visitante")
    split = tm.groupby("condicion").agg(Partidos=("match_id", "count"), Puntos=("puntos", "sum"), GF=("gf", "sum"), GC=("gc", "sum"))
    split["Puntos por partido"] = (split["Puntos"] / split["Partidos"]).round(2)
    st.dataframe(split, width="stretch")

pm = player_match_stats(ev, minutes)
summary = player_summary(pm[pm["team"] == team])
with tab_j:
    cols = ["player", "partidos", "minutos", "goles", "xg", "asistencias", "pases", "pct_pases", "tiros", "presiones", "recuperaciones"]
    tbl = summary[cols].sort_values("minutos", ascending=False).copy()
    tbl["xg"], tbl["pct_pases"] = tbl["xg"].round(2), tbl["pct_pases"].round(1)
    tbl["minutos"] = tbl["minutos"].round(0).astype(int)
    tbl.columns = ["Jugador", "PJ", "Min", "Goles", "xG", "Asist.", "Pases", "% pases", "Tiros", "Presiones", "Recup."]
    st.dataframe(tbl, hide_index=True, width="stretch")
    pc1, pc2 = st.columns([3, 1])
    pick = pc1.selectbox("Abrir la página de un jugador", tbl["Jugador"].tolist(), key="pick_player_equipo")
    pc2.write("")
    if pc2.button("Ver jugador →", type="primary"):
        st.session_state["player"] = pick
        st.switch_page("views/jugador.py")

with tab_m:
    team_ev = ev[ev["team"] == team]
    types = sorted(team_ev["type"].dropna().unique())
    m1, m2 = st.columns(2)
    sel_types = m1.multiselect("Tipos de evento", types, default=[x for x in ["Pass", "Carry"] if x in types], key="map_types_equipo")
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
