import io

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st
from mplsoccer import Pitch

from core import load_scope
import metrica_data
import track_repair
from video_analysis import (PITCH_L, PITCH_W, ROLE_BALL, ROLE_GK, ROLE_PLAYER, ROLE_REF, _event_arrays, _team_positions, best_offset,
                            events_video_time, make_demo_tracks, player_metrics, possession_proxy, statsbomb_to_pitch, sync_score,
                            possession_phases, space_control, space_control_series, team_lines, team_shape, validate_tracks)

st.title("🎥 Vídeo: seguimiento táctico")
st.markdown(
    "Analiza los datos de seguimiento que genera el módulo **football-vision-analyzer** (`tracks.parquet`): "
    "posiciones sobre el campo, mapas de calor, rendimiento físico y forma de cada equipo."
)

# ---------------------------------------------------------------- origen de los datos
src = st.radio("Origen de los datos", ["Datos de demostración", "Metrica Sports (datos reales)", "Subir tracks.parquet", "Desde el analizador (API)"], horizontal=True)
if src == "Datos de demostración":
    if st.button("Cargar demostración (60 s, 22 jugadores)"):
        st.session_state["video_tracks"] = make_demo_tracks(60)
        st.session_state["video_label"] = "Demostración sintética"
elif src == "Metrica Sports (datos reales)":
    st.caption("Seguimiento **real** a 25 Hz de un partido de muestra anonimizado que Metrica Sports publica en GitHub "
               "(github.com/metrica-sports/sample-data). Se descarga al pulsar el botón (≈ 65 MB) y se reduce a 5 Hz. "
               "Úsalo de forma responsable, como pide su repositorio.")
    g = st.radio("Partido de muestra", [1, 2], horizontal=True, key="metrica_game")
    if st.button("Cargar datos reales de Metrica"):
        with st.spinner("Descargando y procesando el partido…"):
            try:
                tracks, _ = metrica_data.load_open_game(int(g), hz=5.0)
                st.session_state["video_tracks"] = tracks
                st.session_state["video_label"] = f"Metrica Sports · partido de muestra {g} (5 Hz)"
                st.session_state["dir_a"] = "la derecha"
            except Exception as e:
                st.error(f"No se pudieron descargar los datos de Metrica: {e}")
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

_label = st.session_state.get("video_label")
if st.session_state.get("video_fixed") is not None and st.session_state.get("video_fixed_label") == _label:
    df = st.session_state["video_fixed"]
    st.success("Se están usando las **trayectorias corregidas** (pestaña «🧵 Corregir IDs»).")
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

# Dirección de ataque del equipo A: la usan las líneas, la estructura y las fases de juego
dir_choice = st.radio("El Equipo A ataca en el vídeo hacia…", ["la derecha", "la izquierda"], horizontal=True, key="dir_a")
ATT = {0: dir_choice == "la derecha", 1: dir_choice != "la derecha"}

tabs = st.tabs(["📍 Posiciones", "🔥 Mapas de calor", "🏃 Rendimiento", "🧩 Forma del equipo", "⚽ Posesión", "🔗 Eventos StatsBomb",
                "🧭 Control del espacio", "📐 Líneas y compacidad", "🧱 Fases de juego", "🧵 Corregir IDs"])

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
        st.caption("Posición suavizada; se ignoran saltos de más de 11 m/s (40 km/h) y huecos de seguimiento de más de 1 s (suelen ser cambios de ID).")
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


# ---------------------------------------------------------------- control del espacio (Voronoi)
with tabs[6]:
    st.markdown("Cada punto del campo se asigna al **equipo del jugador más cercano** (diagramas de Voronoi). Es una medida simple de "
                "territorio: no tiene en cuenta velocidades ni al balón.")
    tmax = float(df["t_seconds"].max())
    t_sp = st.slider("Instante (s)", 0.0, tmax, min(tmax, 30.0), step=1.0, key="space_t")
    a, b, owner = space_control(df, t_sp, include_gk=True, res=1.0)
    if np.isnan(a):
        st.info("En ese instante no hay jugadores de los dos equipos.")
    else:
        from matplotlib.colors import ListedColormap

        m1, m2 = st.columns(2)
        m1.metric(names[0], f"{a * 100:.0f} % del campo")
        m2.metric(names[1], f"{b * 100:.0f} % del campo")
        pitch, fig, ax = new_pitch()
        ax.imshow(owner, extent=[0, PITCH_L, 0, PITCH_W], origin="upper", cmap=ListedColormap([COLORS[0], COLORS[1]]),
                  vmin=0, vmax=1, alpha=0.40, zorder=1, interpolation="nearest")
        now = df.iloc[(df["t_seconds"] - t_sp).abs().argsort()[:1]]["t_seconds"].iat[0]
        cur_sp = df[((df["t_seconds"] - now).abs() < 1e-6) & df["role"].isin([ROLE_PLAYER, ROLE_GK, ROLE_BALL])]
        for team, g in cur_sp[cur_sp["role"] != ROLE_BALL].groupby("team"):
            pitch.scatter(g["x_pitch"], flip(g["y_pitch"]), ax=ax, s=120, c=COLORS[int(team)], edgecolors="black", zorder=5)
        ball = cur_sp[cur_sp["role"] == ROLE_BALL]
        if len(ball):
            pitch.scatter(ball["x_pitch"], flip(ball["y_pitch"]), ax=ax, s=60, c="white", edgecolors="black", zorder=6)
        st.pyplot(fig)
        plt.close(fig)
    key = ("space", st.session_state.get("video_label"), len(df))
    if st.session_state.get("space_key") != key:
        with st.spinner("Calculando la evolución del control del espacio…"):
            st.session_state["space_series"] = space_control_series(df, step_s=max(5.0, tmax / 400), res=2.0)
            st.session_state["space_key"] = key
    ser = st.session_state["space_series"]
    if len(ser):
        roll = ser.set_index(ser["t_seconds"] / 60)[["equipo_0", "equipo_1"]].rolling(6, min_periods=1).mean()
        roll.columns = [names[0], names[1]]
        st.line_chart(roll, height=220)
        st.caption("Cuota de campo de cada equipo a lo largo del tiempo (eje: minutos; suavizado).")

# ---------------------------------------------------------------- líneas y compacidad
with tabs[7]:
    st.markdown("Altura de la **línea defensiva** (los 4 jugadores de campo más retrasados), extensión del equipo y dispersión alrededor de su centroide.")
    lines = {team: team_lines(df, team, ATT[team]) for team in (0, 1)}
    if all(len(v) == 0 for v in lines.values()):
        st.info("No hay jugadores de campo de ningún equipo.")
    else:
        metric = st.selectbox("Métrica", ["linea_def_m", "linea_del_m", "largo_m", "ancho_m", "dispersion_m"],
                              format_func=lambda k: {"linea_def_m": "Altura de la línea defensiva (m desde su portería)", "linea_del_m": "Altura de la línea de ataque (m)",
                                                     "largo_m": "Largo del equipo (m)", "ancho_m": "Ancho del equipo (m)", "dispersion_m": "Dispersión (m al centroide)"}[k], key="lines_metric")
        chart = {}
        for team in (0, 1):
            ln = lines[team]
            if len(ln):
                chart[names[team]] = ln.set_index(ln["t_seconds"] / 60)[metric].rolling(30, min_periods=1).mean()
        st.line_chart(pd.DataFrame(chart), height=260)
        st.caption("Eje: minutos de vídeo. Suavizado con una media móvil. La dirección de ataque se elige arriba.")
        rows = [{"Equipo": names[t], "Línea defensiva (m)": round(lines[t]["linea_def_m"].mean(), 1), "Línea de ataque (m)": round(lines[t]["linea_del_m"].mean(), 1),
                 "Largo (m)": round(lines[t]["largo_m"].mean(), 1), "Ancho (m)": round(lines[t]["ancho_m"].mean(), 1),
                 "Dispersión (m)": round(lines[t]["dispersion_m"].mean(), 1)} for t in (0, 1) if len(lines[t])]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ---------------------------------------------------------------- fases de juego
with tabs[8]:
    st.markdown("Una **fase de posesión** es un tramo seguido en el que un equipo tiene el balón (el jugador más cercano, a menos de la distancia elegida). "
                "Se unen los tramos separados por un balón libre muy breve.")
    c1, c2, c3 = st.columns(3)
    rad = c1.slider("Distancia jugador-balón (m)", 1.0, 6.0, 3.0, 0.5, key="ph_rad")
    min_s = c2.slider("Duración mínima (s)", 1.0, 15.0, 3.0, 0.5, key="ph_min")
    gap = c3.slider("Hueco máximo de balón libre (s)", 0.0, 5.0, 2.0, 0.5, key="ph_gap")
    ph = possession_phases(df, rad, min_s, max_gap_s=gap, attacks_right=ATT)
    if ph.empty:
        st.info("No se detectaron fases con estos parámetros (¿hay balón en el seguimiento?).")
    else:
        k = st.columns(4)
        k[0].metric("Fases", len(ph))
        for i, team in enumerate((0, 1)):
            sub_ph = ph[ph["equipo"] == team]
            k[1 + i].metric(f"{names[team]}: fases · media", f"{len(sub_ph)} · {sub_ph['duracion_s'].mean():.0f} s" if len(sub_ph) else "—")
        k[3].metric("Fase más larga", f"{ph['duracion_s'].max():.0f} s")
        fig, ax = plt.subplots(figsize=(10, 1.8))
        for team in (0, 1):
            sub_ph = ph[ph["equipo"] == team]
            ax.broken_barh(list(zip(sub_ph["t_inicio"] / 60, sub_ph["duracion_s"] / 60)), (team * 10, 8), facecolors=COLORS[team])
        ax.set_yticks([4, 14]); ax.set_yticklabels([names[0], names[1]]); ax.set_xlabel("Minutos de vídeo")
        ax.spines[["top", "right"]].set_visible(False)
        st.pyplot(fig)
        plt.close(fig)
        show = ph.assign(equipo=ph["equipo"].map(names), t_inicio=(ph["t_inicio"] / 60).round(2), t_fin=(ph["t_fin"] / 60).round(2)).round(1)
        show.columns = ["Equipo", "Inicio (min)", "Fin (min)", "Duración (s)", "Balón x inicio (m)", "Balón x fin (m)", "Avance hacia la portería rival (m)"]
        st.dataframe(show.sort_values("Duración (s)", ascending=False), hide_index=True, width="stretch", height=300)
        st.download_button("⬇️ Descargar fases (CSV)", ph.to_csv(index=False).encode("utf-8"), file_name="fases_de_posesion.csv", mime="text/csv")


# ---------------------------------------------------------------- corrección de identidades
with tabs[9]:
    st.markdown(
        "Un seguidor automático suele **partir a un jugador en varias trayectorias** (le da un ID nuevo al reaparecer). Aquí se **cosen** "
        "de forma automática cuando es físicamente plausible (mismo equipo, sin solaparse y donde el jugador habría llegado) y se pueden "
        "corregir a mano. Las demás pestañas usan automáticamente los datos corregidos."
    )
    if st.session_state.get("video_fixed_label") != _label:
        st.session_state["video_fixed"], st.session_state["video_fix_history"], st.session_state["video_fixed_label"] = None, [], _label
    work = df.copy()
    hist = st.session_state.setdefault("video_fix_history", [])

    def commit(new_df, msg):
        hist.append(st.session_state.get("video_fixed") if st.session_state.get("video_fixed") is not None else raw_valid)
        st.session_state["video_fixed"] = new_df
        st.session_state["video_fixed_label"] = _label
        st.session_state["fix_msg"] = msg
        st.rerun()

    raw_valid = validate_tracks(raw)
    frag = track_repair.fragmentation(work)
    k = st.columns(4)
    k[0].metric("Trayectorias de jugador", frag["tracks"], help="Un partido 11 contra 11 debería tener unas 22 (más cambios y expulsiones).")
    k[1].metric("Respecto a las esperadas (22)", f"× {frag['ratio']}")
    k[2].metric("Duración mediana (s)", frag["median_s"])
    k[3].metric("Tiempo en trayectorias largas", f"{frag['share_in_long'] * 100:.0f} %")
    if st.session_state.get("fix_msg"):
        st.success(st.session_state.pop("fix_msg"))

    st.markdown("#### 1) Coser automáticamente")
    c1, c2, c3 = st.columns(3)
    gap = c1.slider("Hueco máximo (s)", 1.0, 10.0, 4.0, 0.5, key="fix_gap")
    dist = c2.slider("Error de predicción máximo (m)", 2.0, 25.0, 8.0, 1.0, key="fix_dist")
    links = track_repair.suggest_links(work, max_gap_s=gap, max_dist_m=dist)
    c3.metric("Uniones propuestas", len(links))
    if len(links):
        with st.expander("Ver las uniones propuestas (de menor a mayor coste)"):
            st.dataframe(links.round(2), hide_index=True, width="stretch")
    b1, b2 = st.columns(2)
    if b1.button("🧵 Aplicar las uniones", type="primary", disabled=len(links) == 0):
        fixed = track_repair.apply_links(work, links)
        commit(fixed, f"{len(links)} uniones aplicadas: de {frag['tracks']} a {track_repair.fragmentation(fixed)['tracks']} trayectorias.")
    if b2.button("↩️ Deshacer el último cambio", disabled=not hist):
        prev = hist.pop()
        st.session_state["video_fixed"] = None if prev is raw_valid else prev
        st.rerun()

    st.markdown("#### 2) Corregir a mano")
    summ = track_repair.track_summary(work)
    summ = summ[summ["role"] != ROLE_BALL].sort_values("t0")
    ids = summ["track_id"].tolist()
    if ids:
        fmt = lambda i: (lambda r: f"#{i} · {names[int(r.team)]} · {r.t0 / 60:.1f}–{r.t1 / 60:.1f} min")(summ[summ["track_id"] == i].iloc[0])
        m1, m2, m3 = st.columns([2, 2, 1])
        keep = m1.selectbox("Mantener la trayectoria", ids, format_func=fmt, key="fix_keep")
        drop = m2.selectbox("…y unirle esta otra", [i for i in ids if i != keep], format_func=fmt, key="fix_drop")
        m3.write("")
        if m3.button("Unir"):
            try:
                commit(track_repair.merge_tracks(work, int(keep), int(drop)), f"#{drop} unido a #{keep}.")
            except ValueError as e:
                st.error(str(e))
        s1, s2, s3 = st.columns([2, 2, 1])
        cut_id = s1.selectbox("Dividir la trayectoria", ids, format_func=fmt, key="fix_cut")
        row = summ[summ["track_id"] == cut_id].iloc[0]
        t_cut = s2.slider("Instante de corte (s)", float(row.t0), float(row.t1), float((row.t0 + row.t1) / 2), key="fix_cut_t")
        s3.write("")
        if s3.button("Dividir"):
            try:
                out, new_id = track_repair.split_track(work, int(cut_id), float(t_cut))
                commit(out, f"#{cut_id} dividido: lo posterior pasa a #{new_id}.")
            except ValueError as e:
                st.error(str(e))
        a1, a2, a3, a4 = st.columns([2, 1, 1, 1])
        sel = a1.selectbox("Cambiar atributos de", ids, format_func=fmt, key="fix_attr")
        team_new = a2.selectbox("Equipo", [0, 1, -1], format_func=lambda k: names[k], key="fix_team")
        role_new = a3.selectbox("Rol", [ROLE_PLAYER, ROLE_GK, ROLE_REF], format_func=lambda r: {0: "Jugador", 1: "Portero", 2: "Árbitro"}[r], key="fix_role")
        a4.write("")
        if a4.button("Aplicar"):
            commit(track_repair.set_attrs(work, int(sel), team_new, role_new), f"#{sel} actualizado.")
        if st.button("🗑️ Eliminar la trayectoria seleccionada arriba"):
            commit(track_repair.delete_track(work, int(sel)), f"#{sel} eliminado.")

    st.markdown("#### 3) Resultado")
    show = summ.assign(Equipo=summ["team"].map(names), inicio=(summ["t0"] / 60).round(2), fin=(summ["t1"] / 60).round(2),
                       duracion_s=(summ["t1"] - summ["t0"]).round(1))[["track_id", "Equipo", "role", "inicio", "fin", "duracion_s", "n"]]
    show.columns = ["ID", "Equipo", "Rol", "Inicio (min)", "Fin (min)", "Duración (s)", "Muestras"]
    st.dataframe(show, hide_index=True, width="stretch", height=260)
    st.download_button("⬇️ Descargar trayectorias corregidas (CSV)", work.to_csv(index=False).encode("utf-8"), file_name="tracks_corregidos.csv", mime="text/csv")
