import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core import (
    COUNT_METRICS, MAP_MODES, draw_pitch_map, extract_xy, load_scope, player_match_stats,
    player_summary, scope_selector, select_player, select_team, team_counts, team_matches, teams_of,
)

matches = st.session_state["matches"]
all_matches = st.session_state["matches_all"]
ICON = {"V": "🟢 V", "E": "🟡 E", "D": "🔴 D"}

st.title("👤 Página de jugador")

teams = teams_of(matches)
cur = st.session_state.get("team")
if cur and cur not in teams:
    teams = sorted(teams + [cur])
top1, top2 = st.columns(2)
with top1:
    team = select_team(teams, key="w_team_jugador", counts=team_counts(all_matches))

base = matches if team in set(teams_of(matches)) else all_matches
tm_all = team_matches(base, team)
if (tm_all["source"] == "StatsBomb").sum() == 0:
    st.info("Este equipo no tiene partidos con eventos detallados.")
    st.stop()
tm, ev, minutes = scope_selector(tm_all, key=f"scope_jugador_{team}")
if ev.empty:
    st.error("No se pudieron cargar los eventos de este equipo.")
    st.stop()

pm_all = player_match_stats(ev, minutes)
summary_all = player_summary(pm_all)
team_summary = summary_all[summary_all["team"] == team]
players = sorted(team_summary.loc[team_summary["minutos"] > 0, "player"].unique())
if not players:
    st.info("No hay jugadores con minutos en este equipo.")
    st.stop()
with top2:
    player = select_player(players, key="w_player_jugador")

pm = pm_all[(pm_all["team"] == team) & (pm_all["player"] == player)]
me = team_summary[team_summary["player"] == player].iloc[0]
pos = ev[(ev["team"] == team) & (ev["player"] == player)]["position"].dropna()
main_pos = pos.mode().iat[0] if len(pos) else "—"

# ---------- Cabecera ----------
st.markdown(f"### {player} · {team} · {main_pos}")
c = st.columns(7)
c[0].metric("Partidos", int(me["partidos"]))
c[1].metric("Minutos", int(round(me["minutos"])))
c[2].metric("Goles", int(me["goles"]))
c[3].metric("xG", f"{me['xg']:.2f}")
c[4].metric("Asistencias", int(me["asistencias"]))
c[5].metric("Pases", int(me["pases"]))
c[6].metric("% pases", "—" if np.isnan(me["pct_pases"]) else f"{me['pct_pases']:.0f}%")

tab_p, tab_c, tab_m = st.tabs(["📅 Partidos jugados", "⚖️ Comparativa", "🗺️ Mapa"])

# ---------- Partidos jugados ----------
with tab_p:
    g = pm.merge(tm, on="match_id", how="left")
    g = g[g["minutos"] > 0].sort_values("match_date")
    st.markdown(f"**{len(g)}** partidos en los que {player} tuvo minutos.")
    t = g.copy()
    t["Resultado"] = t["resultado"].map(ICON)
    t["pct"] = np.where(t["pases"] > 0, t["pases_ok"] / t["pases"] * 100, np.nan).round(1)
    t["xg"] = t["xg"].round(2)
    t["minutos"] = t["minutos"].round(0).astype(int)
    show = t[["match_date", "rival", "condicion", "marcador", "Resultado", "minutos", "goles", "xg", "asistencias", "pases", "pct", "tiros", "presiones", "recuperaciones"]]
    show.columns = ["Fecha", "Rival", "Condición", "Marcador", "Resultado", "Min", "Goles", "xG", "Asist.", "Pases", "% pases", "Tiros", "Presiones", "Recup."]
    st.dataframe(show, hide_index=True, width="stretch")

    metric = st.selectbox("Evolución partido a partido", list(COUNT_METRICS.keys()), format_func=lambda k: COUNT_METRICS[k], key="evo_metric")
    evo = pd.DataFrame({COUNT_METRICS[metric]: g[metric].values}, index=g["match_date"].astype(str) + " vs " + g["rival"])
    st.bar_chart(evo, height=280)

# ---------- Comparativa ----------
PER90 = [k for k in COUNT_METRICS if k != "pases"] + ["pases"]


def hbar(labels, a_vals, b_vals=None, a_name="", b_name="", xlabel="", xlim=None):
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(labels) + 1.2))
    y = np.arange(len(labels))
    if b_vals is None:
        ax.barh(y, a_vals, color="#2a9d8f")
    else:
        ax.barh(y - 0.2, a_vals, height=0.4, color="#2a9d8f", label=a_name)
        ax.barh(y + 0.2, b_vals, height=0.4, color="#e76f51", label=b_name)
        ax.legend(loc="lower right")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    if xlim:
        ax.set_xlim(*xlim)
    ax.spines[["top", "right"]].set_visible(False)
    st.pyplot(fig)
    plt.close(fig)


with tab_c:
    mode = st.radio("Comparar con…", ["Compañeros de equipo", "Otro jugador"], horizontal=True, key="cmp_mode")
    min_minutes = st.slider("Minutos mínimos para entrar en la comparativa", 0, 1500, 300, 30, key="cmp_min")
    st.caption("Las métricas se expresan por 90 minutos para poder compararlas. Ojo: comparar jugadores de posiciones distintas puede ser engañoso.")
    labels = [COUNT_METRICS[k] for k in PER90]
    cols90 = [k + "_90" for k in PER90]

    if mode == "Compañeros de equipo":
        pool = team_summary[team_summary["minutos"] >= min_minutes]
        if player not in set(pool["player"]):
            st.info(f"{player} tiene menos de {min_minutes} minutos. Baja el mínimo para ver su comparativa.")
        elif len(pool) < 3:
            st.info("Hay muy pocos compañeros con esos minutos. Baja el mínimo.")
        else:
            mine90 = pool[pool["player"] == player][cols90].iloc[0]
            pct = [(pool[c] <= mine90[c]).mean() * 100 for c in cols90]
            st.markdown(f"**Percentil de {player} dentro de {len(pool)} jugadores de {team}** (100 = el mejor del equipo)")
            hbar(labels, pct, xlabel="Percentil", xlim=(0, 100))
            table = pd.DataFrame(
                {
                    "Métrica (por 90)": labels,
                    player: [round(mine90[c], 2) for c in cols90],
                    "Media del equipo": [round(pool[c].mean(), 2) for c in cols90],
                    "Percentil": [round(p) for p in pct],
                }
            )
            st.dataframe(table, hide_index=True, width="stretch")
    else:
        b1, b2 = st.columns(2)
        team_b = b1.selectbox("Equipo del otro jugador", teams, index=teams.index(team), key="cmp_team_b")
        if team_b == team:
            ev_b_summary = team_summary
        else:
            tm_b = team_matches(matches, team_b)
            ev_b, min_b = load_scope(tuple(int(i) for i in tm_b["match_id"]))
            sb_all = player_summary(player_match_stats(ev_b, min_b))
            ev_b_summary = sb_all[sb_all["team"] == team_b]
        cand = sorted(ev_b_summary.loc[ev_b_summary["minutos"] >= min_minutes, "player"].unique())
        cand = [p for p in cand if not (team_b == team and p == player)]
        if not cand:
            st.info("No hay jugadores con esos minutos. Baja el mínimo.")
        elif me["minutos"] < min_minutes:
            st.info(f"{player} tiene menos de {min_minutes} minutos. Baja el mínimo.")
        else:
            other = b2.selectbox("Jugador", cand, key="cmp_player_b")
            ob = ev_b_summary[ev_b_summary["player"] == other].iloc[0]
            a_vals = np.array([me[c] for c in cols90], dtype=float)
            b_vals = np.array([ob[c] for c in cols90], dtype=float)
            scale = np.maximum(np.maximum(a_vals, b_vals), 1e-9)
            st.markdown("**Comparativa normalizada** (100 = el mayor de los dos en esa métrica)")
            hbar(labels, a_vals / scale * 100, b_vals / scale * 100, player, other, xlabel="% del mayor valor", xlim=(0, 105))
            table = pd.DataFrame(
                {
                    "Métrica (por 90)": labels + ["% pases", "Minutos", "Partidos"],
                    player: [round(x, 2) for x in a_vals] + [round(me["pct_pases"], 1), int(me["minutos"]), int(me["partidos"])],
                    other: [round(x, 2) for x in b_vals] + [round(ob["pct_pases"], 1), int(ob["minutos"]), int(ob["partidos"])],
                }
            )
            st.dataframe(table, hide_index=True, width="stretch")
            if team_b != team:
                st.caption("Los datos de cada jugador provienen de los partidos de su propio equipo en esta competición.")

# ---------- Mapa ----------
with tab_m:
    pev = ev[(ev["team"] == team) & (ev["player"] == player)]
    types = sorted(pev["type"].dropna().unique())
    defaults = [x for x in ["Pass", "Carry"] if x in types]
    m1, m2 = st.columns(2)
    sel_types = m1.multiselect("Tipos de evento", types, default=defaults, key="map_types_jug")
    mode_map = m2.radio("Representación", MAP_MODES, horizontal=True, key="map_mode_jug")
    lab = {int(r.match_id): f"{r.match_date} vs {r.rival}" for r in tm.itertuples()}
    played = [int(i) for i in pev["match_id"].unique()]
    sel_m = st.multiselect("Partidos (vacío = todos)", played, format_func=lambda k: lab.get(k, str(k)), key="map_matches_jug")
    f = pev
    if sel_types:
        f = f[f["type"].isin(sel_types)]
    if sel_m:
        f = f[f["match_id"].isin(sel_m)]
    st.markdown(f"**{len(f)}** acciones en {len(sel_m) or len(played)} partido(s).")
    draw_pitch_map(extract_xy(f), mode_map)
