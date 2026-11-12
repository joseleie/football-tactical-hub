import io

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st
from mplsoccer import Pitch

from core import load_scope
from video_analysis import (PITCH_L, PITCH_W, ROLE_BALL, ROLE_GK, ROLE_PLAYER, ROLE_REF, _event_arrays, _team_positions, best_offset,
                            events_video_time, make_demo_tracks, player_metrics, possession_proxy, statsbomb_to_pitch, sync_score,
                            team_shape, validate_tracks)

st.title("🎥 Vídeo: seguimiento táctico")
st.markdown(
    "Analiza los datos de seguimiento que genera el módulo **football-vision-analyzer** (`tracks.parquet`): "
    "posiciones sobre el campo, mapas de calor, rendimiento físico y forma de cada equipo."
)

# ---------------------------------------------------------------- origen de los datos
src = st.radio("Origen de los datos", ["Datos de demostración", "Subir tracks.parquet", "Desde el analizador (API)"], horizontal=True)
if src == "Datos de demostración":
    if st.button("Cargar demostración (60 s, 22 jugadores)"):
        st.session_state["video_tracks"] = make_demo_tracks(60)
        st.session_state["video_label"] = "Demostración sintética"
elif src == "Subir tracks.parquet":
    up = st.file_uploader("Archivo tracks.parquet", type=["parquet"])
    if up is not None:
        try:
            st.session_state["video_tracks"] = pd.read_parquet(io.BytesIO(up.getvalue()))
            st.session_state["video_label"] = up.name
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
else:
    c1, c2 = st.columns([3, 2])
    base = c1.text_input("URL del analizador", placeholder="https://mi-servidor.com")
    job = c2.text_input("ID del trabajo (job_id)")
    if st.button("Descargar resultados") and base and job:
        try:
            r = requests.get(f"{base.rstrip('/')}/api/results/{job.strip()}", params={"format": "parquet"}, timeout=60)
            r.raise_for_status()
            st.session_state["video_tracks"] = pd.read_parquet(io.BytesIO(r.content))
            st.session_state["video_label"] = f"Trabajo {job[:8]}…"
        except Exception as e:
            st.error(f"No se pudo descargar: {e}")

raw = st.session_state.get("video_tracks")
if raw is None:
    st.info("Elige un origen de datos para empezar.")
    st.stop()
try:
    df = validate_tracks(raw)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.caption(f"Fuente: {st.session_state.get('video_label', '—')} · {df['frame'].nunique():,} fotogramas · "
           f"{df.loc[df['role'].isin([ROLE_PLAYER, ROLE_GK]), 'track_id'].nunique()} jugadores seguidos · "
           f"{df['t_seconds'].max():.0f} s")

n1, n2 = st.columns(2)
names = {0: n1.text_input("Nombre del equipo A", "Equipo A"), 1: n2.text_input("Nombre del equipo B", "Equipo B"), -1: "Sin equipo"}
COLORS = {0: "#3b82f6", 1: "#ef4444", -1: "#facc15"}

# Pitch en metros. El eje y se invierte para que arriba sea y=0, igual que en el vídeo.
def new_pitch(figsize=(9, 6)):
    p = Pitch(pitch_type="custom", pitch_length=PITCH_L, pitch_width=PITCH_W, pitch_color="grass", line_color="white", line_zorder=2)
    fig, ax = p.draw(figsize=figsize)
    return p, fig, ax

def flip(y):
    return PITCH_W - np.asarray(y, dtype=float)

tabs = st.tabs(["📍 Posiciones", "🔥 Mapas de calor", "🏃 Rendimiento", "🧩 Forma del equipo", "⚽ Posesión", "🔗 Eventos StatsBomb"])

# ---------------------------------------------------------------- posiciones
with tabs[0]:
    tmax = float(df["t_seconds"].max())
    t = st.slider("Instante (s)", 0.0, tmax, 0.0, step=0.5)
    trail = st.slider("Estela (s)", 0, 10, 3)
    window = df[(df["t_seconds"] <= t) & (df["t_seconds"] >= t - max(trail, 0.01))]
    now = df.iloc[(df["t_seconds"] - t).abs().argsort()[:1]]["t_seconds"].iat[0]
    pitch, fig, ax = new_pitch()
    for tid, g in window[window["role"] != ROLE_BALL].groupby("track_id"):
        team = int(g["team"].mode().iat[0])
        pitch.plot(g["x_pitch"], flip(g["y_pitch"]), ax=ax, color=COLORS[team], alpha=0.35, lw=1.5, zorder=3)
    cur = df[(df["t_seconds"] - now).abs() < 1e-6]
    for role, marker, size in ((ROLE_PLAYER, "o", 140), (ROLE_GK, "s", 140), (ROLE_REF, "^", 120), (ROLE_BALL, "o", 60)):
        sub = cur[cur["role"] == role]
        for team, g in sub.groupby("team"):
            pitch.scatter(g["x_pitch"], flip(g["y_pitch"]), ax=ax, s=size, marker=marker, c="white" if role == ROLE_BALL else COLORS[int(team)],
                          edgecolors="black", zorder=5)
    st.pyplot(fig)
    plt.close(fig)

# ---------------------------------------------------------------- calor
with tabs[1]:
    c1, c2 = st.columns(2)
    team_pick = c1.selectbox("Equipo", [0, 1], format_func=lambda k: names[k], key="heat_team")
    cand = df[(df["team"] == team_pick) & df["role"].isin([ROLE_PLAYER, ROLE_GK])]["track_id"].unique()
    picked = c2.multiselect("Jugadores (vacío = todo el equipo)", sorted(cand), format_func=lambda k: f"#{k}", key="heat_players")
    sub = df[(df["team"] == team_pick) & df["role"].isin([ROLE_PLAYER, ROLE_GK])]
    if picked:
        sub = sub[sub["track_id"].isin(picked)]
    pitch, fig, ax = new_pitch()
    if len(sub) > 5:
        bs = pitch.bin_statistic(sub["x_pitch"], flip(sub["y_pitch"]), statistic="count", bins=(21, 14), normalize=True)
        pitch.heatmap(bs, ax=ax, cmap="hot", alpha=0.75, zorder=3)
    st.pyplot(fig)
    plt.close(fig)

# ---------------------------------------------------------------- rendimiento
with tabs[2]:
    m = player_metrics(df)
    if m.empty:
        st.info("No hay suficientes datos de jugadores.")
    else:
        m["Equipo"] = m["team"].map(names)
        show = m[["track_id", "Equipo", "seconds_tracked", "distance_m", "avg_kmh", "max_kmh", "sprint_s"]]
        show.columns = ["Jugador (id)", "Equipo", "Segundos", "Distancia (m)", "Vel. media (km/h)", "Vel. máx. (km/h)", "Sprint (s)"]
        st.dataframe(show, hide_index=True, width="stretch")
        st.bar_chart(m.assign(jugador="#" + m["track_id"].astype(str)).set_index("jugador")["distance_m"], height=280)
        st.caption("Posición suavizada; se ignoran saltos de más de 12,5 m/s y huecos de seguimiento de más de 1 s (suelen ser cambios de ID).")
        st.download_button("⬇️ Descargar métricas (CSV)", m.to_csv(index=False).encode("utf-8"), file_name="metricas_jugadores.csv", mime="text/csv")

# ---------------------------------------------------------------- forma
with tabs[3]:
    tmax = float(df["t_seconds"].max())
    t0, t1 = st.slider("Ventana de tiempo (s)", 0.0, tmax, (0.0, min(tmax, 20.0)), step=0.5, key="shape_win")
    pitch, fig, ax = new_pitch()
    rows = []
    for team in (0, 1):
        s = team_shape(df, team, t0, t1)
        if s["centroid"] is None:
            continue
        pl = s["players"]
        pitch.scatter(pl["x_pitch"], flip(pl["y_pitch"]), ax=ax, s=160, c=COLORS[team], edgecolors="black", zorder=5)
        if len(s["hull"]) >= 3:
            h = s["hull"]
            ax.fill(h[:, 0], flip(h[:, 1]), color=COLORS[team], alpha=0.18, zorder=2)
            ax.plot(np.r_[h[:, 0], h[0, 0]], np.r_[flip(h[:, 1]), flip(h[0, 1])], color=COLORS[team], lw=2, zorder=4)
        pitch.scatter([s["centroid"][0]], [flip(s["centroid"][1])], ax=ax, s=260, marker="X", c="white", edgecolors=COLORS[team], linewidth=2, zorder=6)
        rows.append({"Equipo": names[team], "Largo (m)": round(s["length_m"], 1), "Ancho (m)": round(s["width_m"], 1),
                     "Área (m²)": round(s["area_m2"]), "Centroide x (m)": round(s["centroid"][0], 1)})
    st.pyplot(fig)
    plt.close(fig)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Posición media de cada jugador de campo en la ventana, su envolvente convexa y el centroide (X).")

# ---------------------------------------------------------------- posesión
with tabs[4]:
    radius = st.slider("Distancia máxima jugador-balón (m)", 1.0, 6.0, 3.0, 0.5)
    p = possession_proxy(df, radius)
    if p["frames"] == 0:
        st.info("No hay fotogramas con balón y jugadores.")
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric(names[0], f"{p['0'] * 100:.0f} %")
        k2.metric(names[1], f"{p['1'] * 100:.0f} %")
        k3.metric("Balón libre", f"{p['libre'] * 100:.0f} %")
        st.caption("Aproximación: en cada fotograma gana el equipo del jugador más cercano al balón, si está dentro de la distancia elegida.")

# ---------------------------------------------------------------- cruce con eventos de StatsBomb
with tabs[5]:
    st.markdown(
        "Superpone los **eventos de StatsBomb** (pases, conducciones, tiros) sobre el seguimiento del vídeo. Para ello hay que "
        "indicar **qué partido es**, qué equipo es el A y **en qué segundo del vídeo empieza la 1.ª parte**; el botón de abajo "
        "busca ese desfase automáticamente comparando la posición de cada evento con la del jugador más cercano."
    )
    allm = st.session_state["matches_all"]
    scopes = (allm.assign(scope=allm["competition"] + " · " + allm["season"]).groupby("scope")["match_date"].max()
              .sort_values(ascending=False).index.tolist())
    c1, c2 = st.columns(2)
    scope = c1.selectbox("Competición · temporada", scopes, key="sync_scope")
    sub = allm[(allm["competition"] + " · " + allm["season"]) == scope].sort_values("match_date", ascending=False)
    labels = {int(r.match_id): f"{r.home_team} {int(r.home_score)}-{int(r.away_score)} {r.away_team} ({r.match_date})" for r in sub.itertuples()}
    mid = c2.selectbox("Partido", list(labels.keys()), format_func=lambda k: labels[k], key="sync_match")
    ev_all, _ = load_scope((int(mid),))
    teams_real = [t for t in ev_all["team"].dropna().unique()]
    if len(teams_real) != 2:
        st.warning("No se pudieron cargar los eventos de ese partido.")
        st.stop()
    d1, d2 = st.columns(2)
    a_real = d1.selectbox("El «Equipo A» del vídeo es…", teams_real, key="sync_a")
    b_real = teams_real[0] if a_real == teams_real[1] else teams_real[1]
    dir_a = d2.radio(f"{a_real} ataca en el vídeo hacia…", ["la derecha", "la izquierda"], horizontal=True, key="sync_dir")
    real = {0: a_real, 1: b_real}
    attacks = {0: dir_a == "la derecha", 1: dir_a != "la derecha"}

    st.session_state.setdefault("sync_offset", 0.0)
    if st.button("🔎 Buscar el desfase automáticamente"):
        best, score, curve = best_offset(df, 0, ev_all[ev_all["team"] == a_real], attacks[0], period=1)
        if np.isfinite(score):
            st.session_state["sync_offset"] = float(best)
            st.session_state["sync_curve"] = curve
        else:
            st.warning("No hay suficientes eventos comparables con este seguimiento (¿el clip es muy corto o el partido no coincide?).")
    offset = st.number_input("Segundo del vídeo en que empieza la 1.ª parte", key="sync_offset", step=1.0)

    ev1 = ev_all[ev_all["period"] == 1]
    scores = {}
    for team in (0, 1):
        times, pos = _team_positions(df, team)
        t_game, px, py = _event_arrays(ev1[ev1["team"] == real[team]], attacks[team], 1)
        scores[team] = sync_score(times, pos, t_game, px, py, float(offset))
    ok = [v for v in scores.values() if np.isfinite(v)]
    if ok:
        q = float(np.mean(ok))
        verdict = "buena" if q < 3 else "regular" if q < 8 else "mala"
        st.metric("Calidad de la alineación (mediana de distancia evento-jugador)", f"{q:.1f} m", help="Menos de 3 m: buena. Más de 8 m: probablemente el desfase, el equipo o la dirección son incorrectos.")
        st.caption(f"Alineación {verdict}.")
    else:
        st.info("Con este desfase no coinciden suficientes eventos con el tramo de vídeo cargado.")
    if st.session_state.get("sync_curve") is not None:
        curve = st.session_state["sync_curve"]
        st.line_chart(curve.replace(np.inf, np.nan).rename("distancia mediana (m)"), height=180)

    tmax = float(df["t_seconds"].max())
    t = st.slider("Instante del vídeo (s)", 0.0, tmax, min(tmax, 10.0), step=0.5, key="sync_t")
    win = st.slider("Ventana de eventos (± s)", 1, 15, 5, key="sync_win")
    pitch, fig, ax = new_pitch()
    now = df.iloc[(df["t_seconds"] - t).abs().argsort()[:1]]["t_seconds"].iat[0]
    cur = df[((df["t_seconds"] - now).abs() < 1e-6) & (df["role"] != ROLE_BALL)]
    for team, g in cur.groupby("team"):
        pitch.scatter(g["x_pitch"], flip(g["y_pitch"]), ax=ax, s=110, c=COLORS[int(team)], edgecolors="black", alpha=0.85, zorder=4)
    rows = []
    for team in (0, 1):
        evt = events_video_time(ev_all[(ev_all["team"] == real[team]) & ev_all["type"].isin(["Pass", "Shot", "Carry"])], float(offset))
        evt = evt[(evt["t_video"] >= t - win) & (evt["t_video"] <= t + win) & evt["location"].notna()]
        for r in evt.itertuples():
            if not isinstance(r.location, (list, tuple, np.ndarray)) or len(r.location) < 2:
                continue
            x, y = statsbomb_to_pitch(r.location[0], r.location[1], attacks[team])
            marker = "*" if r.type == "Shot" else "D"
            pitch.scatter([float(x)], [float(PITCH_W - y)], ax=ax, s=260 if r.type == "Shot" else 90, marker=marker, c="white",
                          edgecolors=COLORS[team], linewidth=2, zorder=6)
            rows.append({"t vídeo (s)": round(float(r.t_video), 1), "Equipo": real[team], "Jugador": r.player, "Evento": r.type})
    st.pyplot(fig)
    plt.close(fig)
    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values("t vídeo (s)"), hide_index=True, width="stretch")
    else:
        st.caption("No hay eventos en esa ventana de tiempo.")
    st.caption("Círculos: jugadores seguidos en el vídeo. Rombos y estrellas: eventos de StatsBomb (estrella = tiro).")
