"""Análisis de los datos de seguimiento del módulo de vídeo (football-vision-analyzer).

Entrada: DataFrame con el contrato de `tracks.parquet`: frame, t_seconds, track_id, role, team, x_pitch, y_pitch
(metros sobre el campo de 105 x 68; role: 0 jugador, 1 portero, 2 árbitro, 3 balón; team: 0 = A, 1 = B, -1 = ninguno).
Son funciones puras de pandas/numpy, sin Streamlit, para poder probarlas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PITCH_L, PITCH_W = 105.0, 68.0
ROLE_PLAYER, ROLE_GK, ROLE_REF, ROLE_BALL = 0, 1, 2, 3
REQUIRED = ["frame", "t_seconds", "track_id", "role", "team", "x_pitch", "y_pitch"]


def validate_tracks(df: pd.DataFrame) -> pd.DataFrame:
    """Comprueba el contrato y devuelve solo las filas con posición en el campo."""
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas del contrato: {missing}")
    out = df.dropna(subset=["x_pitch", "y_pitch"]).copy()
    if out.empty:
        raise ValueError("El archivo no tiene posiciones sobre el campo: el vídeo se procesó sin calibrar la homografía.")
    # Se descartan puntos claramente fuera del campo (errores de seguimiento o de calibración)
    inside = out["x_pitch"].between(-5, PITCH_L + 5) & out["y_pitch"].between(-5, PITCH_W + 5)
    return out[inside].sort_values(["track_id", "t_seconds"]).reset_index(drop=True)


def player_metrics(df: pd.DataFrame, max_speed_ms: float = 11.0, smooth: int = 3, sprint_kmh: float = 24.0,
                   max_gap_s: float = 1.0) -> pd.DataFrame:
    """Distancia, velocidad media/máxima y tiempo en sprint por jugador (portero incluido).

    Se suaviza la posición con una media móvil y se ignoran los saltos físicamente imposibles
    (> max_speed_ms) o con huecos de seguimiento (> max_gap_s), que suelen ser cambios de ID o ruido.
    """
    rows = []
    for tid, g in df[df["role"].isin([ROLE_PLAYER, ROLE_GK])].groupby("track_id"):
        g = g.sort_values("t_seconds")
        x = g["x_pitch"].rolling(smooth, center=True, min_periods=1).mean().to_numpy()
        y = g["y_pitch"].rolling(smooth, center=True, min_periods=1).mean().to_numpy()
        t = g["t_seconds"].to_numpy()
        if len(g) < 2:
            continue
        dt = np.diff(t)
        step = np.hypot(np.diff(x), np.diff(y))
        with np.errstate(divide="ignore", invalid="ignore"):
            speed = np.where(dt > 0, step / dt, np.nan)
        ok = (dt > 0) & (dt <= max_gap_s) & (speed <= max_speed_ms)
        moving_time = float(dt[ok].sum())
        dist = float(step[ok].sum())
        kmh = speed[ok] * 3.6
        rows.append({
            "track_id": int(tid), "team": int(g["team"].mode().iat[0]), "role": int(g["role"].mode().iat[0]),
            "seconds_tracked": round(float(t[-1] - t[0]), 1), "distance_m": round(dist, 1),
            "avg_kmh": round(dist / moving_time * 3.6, 2) if moving_time > 0 else 0.0,
            "max_kmh": round(float(kmh.max()), 1) if len(kmh) else 0.0,
            "sprint_s": round(float(dt[ok][kmh >= sprint_kmh].sum()), 1),
            "mean_x": round(float(g["x_pitch"].mean()), 1), "mean_y": round(float(g["y_pitch"].mean()), 1),
        })
    cols = ["track_id", "team", "role", "seconds_tracked", "distance_m", "avg_kmh", "max_kmh", "sprint_s", "mean_x", "mean_y"]
    return pd.DataFrame(rows, columns=cols).sort_values("distance_m", ascending=False).reset_index(drop=True)


def convex_hull(points: np.ndarray) -> np.ndarray:
    """Envolvente convexa (algoritmo de la cadena monótona). Devuelve los vértices en orden."""
    pts = sorted({(round(float(x), 6), round(float(y), 6)) for x, y in points})
    if len(pts) <= 2:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def polygon_area(poly: np.ndarray) -> float:
    if len(poly) < 3:
        return 0.0
    x, y = poly[:, 0], poly[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def team_shape(df: pd.DataFrame, team: int, t_start: float | None = None, t_end: float | None = None,
               include_gk: bool = False) -> dict:
    """Forma del equipo en una ventana de tiempo: posición media de cada jugador, centroide, largo, ancho y área."""
    roles = [ROLE_PLAYER, ROLE_GK] if include_gk else [ROLE_PLAYER]
    g = df[(df["team"] == team) & df["role"].isin(roles)]
    if t_start is not None:
        g = g[g["t_seconds"] >= t_start]
    if t_end is not None:
        g = g[g["t_seconds"] <= t_end]
    means = g.groupby("track_id")[["x_pitch", "y_pitch"]].mean()
    if len(means) == 0:
        return {"players": means, "centroid": None, "length_m": 0.0, "width_m": 0.0, "area_m2": 0.0, "hull": np.empty((0, 2))}
    pts = means.to_numpy()
    hull = convex_hull(pts)
    return {"players": means, "centroid": (float(pts[:, 0].mean()), float(pts[:, 1].mean())),
            "length_m": float(np.ptp(pts[:, 0])), "width_m": float(np.ptp(pts[:, 1])),
            "area_m2": polygon_area(hull), "hull": hull}


def possession_proxy(df: pd.DataFrame, radius_m: float = 3.0) -> dict:
    """Posesión aproximada: en cada fotograma con balón, gana el equipo del jugador más cercano si está a <= radius_m."""
    ball = df[df["role"] == ROLE_BALL].drop_duplicates("frame").set_index("frame")[["x_pitch", "y_pitch"]]
    players = df[df["role"].isin([ROLE_PLAYER, ROLE_GK]) & (df["team"] >= 0)]
    counts = {0: 0, 1: 0, "libre": 0}
    for frame, g in players.groupby("frame"):
        if frame not in ball.index:
            continue
        bx, by = ball.loc[frame, "x_pitch"], ball.loc[frame, "y_pitch"]
        d = np.hypot(g["x_pitch"].to_numpy() - bx, g["y_pitch"].to_numpy() - by)
        k = int(d.argmin())
        counts[int(g["team"].iat[k]) if d[k] <= radius_m else "libre"] += 1
    total = sum(counts.values())
    return {"frames": total, **{str(k): (v / total if total else 0.0) for k, v in counts.items()}}


def make_demo_tracks(seconds: float = 60.0, fps: float = 10.0, seed: int = 7) -> pd.DataFrame:
    """Datos de demostración con el mismo contrato que `tracks.parquet`: 2 equipos de 11, árbitro y balón."""
    rng = np.random.default_rng(seed)
    n = int(seconds * fps)
    t = np.arange(n) / fps
    # Formaciones base (x a lo largo del campo, y a lo ancho). El equipo A ataca hacia la derecha.
    lines = [(8, [34]), (28, [12, 26, 42, 56]), (50, [12, 26, 42, 56]), (72, [24, 44])]
    base_a = np.array([(x, y) for x, ys in lines for y in ys], float)
    base_b = np.column_stack([PITCH_L - base_a[:, 0], PITCH_W - base_a[:, 1]])
    rows = []
    tid = 0

    def smooth_walk(scale):  # paseo aleatorio suave (media móvil de ruido)
        w = np.cumsum(rng.normal(0, scale, n))
        k = int(fps * 3)
        return np.convolve(w - w.mean(), np.ones(k) / k, mode="same")

    ball_x = np.clip(PITCH_L / 2 + 25 * np.sin(t / 7) + smooth_walk(0.8), 2, PITCH_L - 2)
    ball_y = np.clip(PITCH_W / 2 + 18 * np.cos(t / 5) + smooth_walk(0.6), 2, PITCH_W - 2)
    for team, base in ((0, base_a), (1, base_b)):
        for k, (bx, by) in enumerate(base):
            role = ROLE_GK if k == 0 else ROLE_PLAYER
            # Cada jugador se desplaza hacia el balón en proporción a su posición (bloque que se mueve unido)
            pull = 0.35 if role == ROLE_PLAYER else 0.05
            x = np.clip(bx + pull * (ball_x - PITCH_L / 2) + smooth_walk(1.2) * 1.5, 0, PITCH_L)
            y = np.clip(by + pull * (ball_y - PITCH_W / 2) + smooth_walk(1.0) * 1.5, 0, PITCH_W)
            rows.append(pd.DataFrame({"frame": (t * 30).astype(int), "t_seconds": t, "track_id": tid, "role": role,
                                      "team": team, "x_pitch": x, "y_pitch": y}))
            tid += 1
    ref_x = np.clip(PITCH_L / 2 + 20 * np.sin(t / 9), 0, PITCH_L)
    rows.append(pd.DataFrame({"frame": (t * 30).astype(int), "t_seconds": t, "track_id": tid, "role": ROLE_REF,
                              "team": -1, "x_pitch": ref_x, "y_pitch": PITCH_W / 2 + 8 * np.cos(t / 6)}))
    rows.append(pd.DataFrame({"frame": (t * 30).astype(int), "t_seconds": t, "track_id": -1, "role": ROLE_BALL,
                              "team": -1, "x_pitch": ball_x, "y_pitch": ball_y}))
    return pd.concat(rows, ignore_index=True)


# =====================================================================
# Cruce temporal con los eventos de StatsBomb
# =====================================================================
SB_L, SB_W = 120.0, 80.0  # el campo de StatsBomb va de 0 a 120 en x y de 0 a 80 en y (y = 0 arriba)
SYNC_TYPES = ("Pass", "Shot", "Carry")  # eventos cuya localización es la del jugador que actúa


def statsbomb_to_pitch(x, y, attacks_right: bool = True):
    """Coordenadas de StatsBomb -> metros del campo de 105 x 68.

    StatsBomb orienta SIEMPRE los eventos de cada equipo de izquierda a derecha. Si en el vídeo ese equipo ataca
    hacia la izquierda (`attacks_right=False`), se gira el plano 180°.
    """
    px = np.asarray(x, dtype=float) * PITCH_L / SB_L
    py = np.asarray(y, dtype=float) * PITCH_W / SB_W
    return (px, py) if attacks_right else (PITCH_L - px, PITCH_W - py)


def pitch_to_statsbomb(px, py, attacks_right: bool = True):
    px, py = np.asarray(px, dtype=float), np.asarray(py, dtype=float)
    if not attacks_right:
        px, py = PITCH_L - px, PITCH_W - py
    return px * SB_L / PITCH_L, py * SB_W / PITCH_W


def events_video_time(ev: pd.DataFrame, offset_p1: float, offset_p2: float | None = None) -> pd.DataFrame:
    """Añade `t_video` (segundos de vídeo) a los eventos: offset_p1 = instante del vídeo en que empieza la 1.ª parte,
    offset_p2 = instante en que empieza la 2.ª. Sin offset_p2 se descartan los eventos de la 2.ª parte."""
    e = ev[ev["period"].isin([1, 2])].copy()
    game_s = e["minute"].astype(float) * 60 + e["second"].astype(float)
    e["t_video"] = np.where(e["period"] == 1, offset_p1 + game_s,
                            (offset_p2 + game_s - 45 * 60) if offset_p2 is not None else np.nan)
    return e.dropna(subset=["t_video"])


def _team_positions(tracks: pd.DataFrame, team: int, roles=(ROLE_PLAYER, ROLE_GK)):
    """Tensor (T, P, 2) con la posición de cada jugador del equipo en cada instante (NaN si no hay dato)."""
    g = tracks[(tracks["team"] == team) & tracks["role"].isin(list(roles))]
    times = np.sort(g["t_seconds"].unique())
    ids = np.sort(g["track_id"].unique())
    pos = np.full((len(times), len(ids), 2), np.nan)
    ti = np.searchsorted(times, g["t_seconds"].to_numpy())
    pi = np.searchsorted(ids, g["track_id"].to_numpy())
    pos[ti, pi, 0], pos[ti, pi, 1] = g["x_pitch"].to_numpy(), g["y_pitch"].to_numpy()
    return times, pos


def _event_arrays(events: pd.DataFrame, attacks_right: bool, period: int | None):
    e = events[events["type"].isin(SYNC_TYPES) & events["location"].notna()]
    if period is not None:
        e = e[e["period"] == period]
    loc = np.array([[l[0], l[1]] for l in e["location"] if isinstance(l, (list, tuple, np.ndarray)) and len(l) >= 2], dtype=float)
    keep = e["location"].apply(lambda l: isinstance(l, (list, tuple, np.ndarray)) and len(l) >= 2).to_numpy()
    e = e[keep]
    if len(loc) == 0:
        return np.empty(0), np.empty(0), np.empty(0)
    px, py = statsbomb_to_pitch(loc[:, 0], loc[:, 1], attacks_right)
    return (e["minute"].astype(float) * 60 + e["second"].astype(float)).to_numpy(), px, py


def sync_score(times, pos, t_game, px, py, offset: float, max_gap_s: float = 1.0, min_events: int = 8) -> float:
    """Mediana (m) de la distancia entre cada evento y el jugador del mismo equipo más cercano en ese instante.
    Cuanto más baja, mejor alineados están vídeo y eventos. inf si hay pocos eventos comparables."""
    if len(times) == 0 or len(t_game) == 0:
        return float("inf")
    tv = t_game + offset
    idx = np.clip(np.searchsorted(times, tv), 1, len(times) - 1)
    idx = np.where(np.abs(times[idx - 1] - tv) <= np.abs(times[idx] - tv), idx - 1, idx)
    ok = np.abs(times[idx] - tv) <= max_gap_s
    if ok.sum() < min_events:
        return float("inf")
    d = np.hypot(pos[idx[ok], :, 0] - px[ok, None], pos[idx[ok], :, 1] - py[ok, None])
    nearest = np.nanmin(np.where(np.isnan(d), np.inf, d), axis=1)
    nearest = nearest[np.isfinite(nearest)]
    return float(np.median(nearest)) if len(nearest) >= min_events else float("inf")


def best_offset_xy(tracks: pd.DataFrame, team: int, t_game, px, py, search: tuple[float, float] = (-600.0, 600.0),
                   step: float = 1.0) -> tuple[float, float, pd.Series]:
    """Busca el desfase vídeo-eventos con eventos ya en metros (t_game en segundos de partido). Sirve para cualquier
    proveedor de eventos. Devuelve (offset, puntuación = mediana de distancia en m, curva completa)."""
    times, pos = _team_positions(tracks, team)
    t_game, px, py = np.asarray(t_game, float), np.asarray(px, float), np.asarray(py, float)
    offsets = np.arange(search[0], search[1] + step, step)
    scores = np.array([sync_score(times, pos, t_game, px, py, o) for o in offsets])
    curve = pd.Series(scores, index=offsets)
    if not np.isfinite(scores).any():
        return float("nan"), float("inf"), curve
    i = int(np.argmin(scores))
    return float(offsets[i]), float(scores[i]), curve


def best_offset(tracks: pd.DataFrame, team: int, events: pd.DataFrame, attacks_right: bool, period: int = 1,
                search: tuple[float, float] = (-600.0, 600.0), step: float = 1.0) -> tuple[float, float, pd.Series]:
    """Como `best_offset_xy`, con eventos de StatsBomb (coordenadas 120 x 80 y minuto/segundo)."""
    t_game, px, py = _event_arrays(events, attacks_right, period)
    return best_offset_xy(tracks, team, t_game, px, py, search, step)


# =====================================================================
# Análisis táctico sobre el seguimiento (control del espacio, líneas, fases de juego)
# =====================================================================
def _nearest_time(df: pd.DataFrame, t: float) -> float:
    times = df["t_seconds"].to_numpy()
    return float(times[np.abs(times - t).argmin()])


def space_control(df: pd.DataFrame, t: float, include_gk: bool = True, res: float = 1.0):
    """Control del espacio por Voronoi: cada punto del campo pertenece al equipo del jugador más cercano.
    Devuelve (cuota equipo 0, cuota equipo 1, matriz de propietarios con 0/1) en una rejilla de `res` metros."""
    now = _nearest_time(df, t)
    roles = [ROLE_PLAYER, ROLE_GK] if include_gk else [ROLE_PLAYER]
    g = df[((df["t_seconds"] - now).abs() < 1e-6) & df["role"].isin(roles) & (df["team"] >= 0)]
    xs, ys = np.arange(res / 2, PITCH_L, res), np.arange(res / 2, PITCH_W, res)
    gx, gy = np.meshgrid(xs, ys)
    if g["team"].nunique() < 2:
        return float("nan"), float("nan"), np.full(gx.shape, -1)
    pos, team = g[["x_pitch", "y_pitch"]].to_numpy(), g["team"].to_numpy()
    d2 = (gx[..., None] - pos[:, 0]) ** 2 + (gy[..., None] - pos[:, 1]) ** 2
    owner = team[d2.argmin(axis=-1)]
    return float((owner == 0).mean()), float((owner == 1).mean()), owner


def space_control_series(df: pd.DataFrame, step_s: float = 5.0, res: float = 2.0, include_gk: bool = True) -> pd.DataFrame:
    """Cuota de espacio de cada equipo a lo largo del tiempo (una muestra cada `step_s` segundos)."""
    rows = []
    for t in np.arange(df["t_seconds"].min(), df["t_seconds"].max(), step_s):
        a, b, _ = space_control(df, t, include_gk, res)
        if not np.isnan(a):
            rows.append({"t_seconds": t, "equipo_0": a, "equipo_1": b})
    return pd.DataFrame(rows, columns=["t_seconds", "equipo_0", "equipo_1"])


def team_lines(df: pd.DataFrame, team: int, attacks_right: bool = True, k: int = 4, min_outfield: int = 6) -> pd.DataFrame:
    """Serie temporal de estructura del equipo (jugadores de campo):
    linea_def_m = distancia media a la propia portería de los k jugadores más retrasados (altura de la línea defensiva),
    linea_del_m = idem de los k más adelantados, largo_m y ancho_m = extensión del equipo y dispersion_m = distancia media al centroide."""
    import warnings

    times, pos = _team_positions(df, team, roles=(ROLE_PLAYER,))
    cols = ["t_seconds", "linea_def_m", "linea_del_m", "largo_m", "ancho_m", "dispersion_m"]
    if len(times) == 0:
        return pd.DataFrame(columns=cols)
    x, y = pos[:, :, 0], pos[:, :, 1]
    own = x if attacks_right else PITCH_L - x
    valid = (~np.isnan(own)).sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        asc = np.sort(own, axis=1)               # los NaN quedan al final
        desc = -np.sort(-own, axis=1)
        dist = np.hypot(x - np.nanmean(x, axis=1, keepdims=True), y - np.nanmean(y, axis=1, keepdims=True))
        out = pd.DataFrame({
            "t_seconds": times,
            "linea_def_m": np.nanmean(asc[:, :k], axis=1), "linea_del_m": np.nanmean(desc[:, :k], axis=1),
            "largo_m": np.nanmax(own, axis=1) - np.nanmin(own, axis=1),
            "ancho_m": np.nanmax(y, axis=1) - np.nanmin(y, axis=1), "dispersion_m": np.nanmean(dist, axis=1)})
    out.loc[valid < min_outfield, cols[1:]] = np.nan
    return out


def possession_phases(df: pd.DataFrame, radius_m: float = 3.0, min_s: float = 3.0, smooth_s: float = 1.0,
                      max_gap_s: float = 2.0, attacks_right: dict | None = None) -> pd.DataFrame:
    """Fases de posesión: tramos seguidos en los que un equipo tiene el balón (el jugador más cercano, a <= radius_m).
    Se suaviza con un filtro de mayoría, se unen los tramos del mismo equipo separados por <= max_gap_s de balón libre
    y se descartan las fases de menos de min_s. Devuelve inicio, fin, duración y avance del balón en metros."""
    attacks_right = attacks_right or {0: True, 1: False}
    pl = df[df["role"].isin([ROLE_PLAYER, ROLE_GK]) & (df["team"] >= 0)]
    ball = df[df["role"] == ROLE_BALL].drop_duplicates("t_seconds").set_index("t_seconds").sort_index()
    cols = ["equipo", "t_inicio", "t_fin", "duracion_s", "balon_x_inicio", "balon_x_fin", "avance_m"]
    if ball.empty or pl.empty:
        return pd.DataFrame(columns=cols)
    times = ball.index.to_numpy()
    ids = np.sort(pl["track_id"].unique())
    pos = np.full((len(times), len(ids), 2), np.nan)
    sub = pl[pl["t_seconds"].isin(times)]
    pos[np.searchsorted(times, sub["t_seconds"].to_numpy()), np.searchsorted(ids, sub["track_id"].to_numpy())] = sub[["x_pitch", "y_pitch"]].to_numpy()
    team_of = pl.groupby("track_id")["team"].agg(lambda s: s.mode().iat[0]).reindex(ids).to_numpy()
    bxy = ball[["x_pitch", "y_pitch"]].to_numpy()
    d = np.hypot(pos[:, :, 0] - bxy[:, None, 0], pos[:, :, 1] - bxy[:, None, 1])
    d = np.where(np.isnan(d), np.inf, d)
    near = d.argmin(axis=1)
    owner = np.where(d[np.arange(len(times)), near] <= radius_m, team_of[near], -1)
    step = float(np.median(np.diff(times))) if len(times) > 1 else 0.2
    w = max(1, int(round(smooth_s / step)) | 1)  # ventana impar
    if w > 1:  # filtro de mayoría sobre {-1, 0, 1}
        votes = np.stack([np.convolve((owner == c).astype(float), np.ones(w), mode="same") for c in (-1, 0, 1)], axis=1)
        owner = np.array([-1, 0, 1])[votes.argmax(axis=1)]
    # tramos consecutivos
    runs, start = [], 0
    for i in range(1, len(owner) + 1):
        if i == len(owner) or owner[i] != owner[start]:
            runs.append([int(owner[start]), start, i - 1])
            start = i
    merged = []
    for r in runs:  # unir tramos del mismo equipo separados por un hueco corto de balón libre
        if (merged and r[0] >= 0 and merged[-1][0] == r[0]):
            merged[-1][2] = r[2]
        elif (len(merged) >= 2 and r[0] >= 0 and merged[-1][0] == -1 and merged[-2][0] == r[0]
              and (times[merged[-1][2]] - times[merged[-1][1]] + step) <= max_gap_s):
            merged.pop()
            merged[-1][2] = r[2]
        else:
            merged.append(r)
    rows = []
    for team, a, b in merged:
        dur = float(times[b] - times[a] + step)
        if team < 0 or dur < min_s:
            continue
        x0, x1 = float(bxy[a, 0]), float(bxy[b, 0])
        adv = (x1 - x0) if attacks_right.get(team, True) else (x0 - x1)
        rows.append({"equipo": team, "t_inicio": float(times[a]), "t_fin": float(times[b]), "duracion_s": dur,
                     "balon_x_inicio": x0, "balon_x_fin": x1, "avance_m": adv})
    return pd.DataFrame(rows, columns=cols)
