"""Reparación de identidades en los datos de seguimiento: unir trayectorias fragmentadas y corregirlas a mano.

Los seguidores automáticos pierden a un jugador (oclusión, salida de plano) y, al reaparecer, le dan un ID nuevo:
un jugador real acaba repartido en varias trayectorias («tracklets»). Aquí se cosen de forma automática cuando es
físicamente plausible y se ofrecen operaciones manuales para el resto. Funciona sobre el contrato del hub
(track_id, t_seconds, x_pitch, y_pitch, team, role) y no usa Streamlit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

ROLE_PLAYER, ROLE_GK, ROLE_REF, ROLE_BALL = 0, 1, 2, 3
PERSON_ROLES = (ROLE_PLAYER, ROLE_GK, ROLE_REF)
X, Y = "x_pitch", "y_pitch"


def track_summary(df: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """Una fila por trayectoria: inicio, fin, posiciones y velocidad media al principio y al final."""
    rows = []
    for tid, g in df[df["track_id"] >= 0].groupby("track_id"):
        g = g.sort_values("t_seconds")
        t, x, y = g["t_seconds"].to_numpy(), g[X].to_numpy(), g[Y].to_numpy()

        def vel(a, b):  # velocidad media entre las muestras a..b (m/s)
            dt = t[b] - t[a]
            return ((x[b] - x[a]) / dt, (y[b] - y[a]) / dt) if dt > 0 else (0.0, 0.0)

        n = len(g)
        kk = min(k, n - 1)
        v0 = vel(0, kk) if n > 1 else (0.0, 0.0)
        v1 = vel(n - 1 - kk, n - 1) if n > 1 else (0.0, 0.0)
        rows.append({"track_id": int(tid), "n": n, "t0": t[0], "t1": t[-1], "x0": x[0], "y0": y[0], "x1": x[-1], "y1": y[-1],
                     "vx0": v0[0], "vy0": v0[1], "vx1": v1[0], "vy1": v1[1],
                     "team": int(g["team"].mode().iat[0]), "role": int(g["role"].mode().iat[0])})
    return pd.DataFrame(rows)


def suggest_links(df: pd.DataFrame, max_gap_s: float = 4.0, max_dist_m: float = 8.0, vmax_ms: float = 11.0,
                  min_overlap_tol_s: float = 0.0) -> pd.DataFrame:
    """Propone qué trayectoria continúa a cuál. Cada una tiene como mucho un sucesor y un predecesor (asignación óptima).

    Una unión a → b es posible si: mismo equipo y mismo tipo de rol, b empieza después de que termine a (sin solapes),
    el hueco es de ≤ max_gap_s, y b aparece donde a habría llegado moviéndose con su velocidad (error ≤ max_dist_m) sin
    exigir más de vmax_ms. El coste es ese error de predicción más una pequeña penalización por hueco.
    Devuelve: from_id, to_id, gap_s, dist_m, cost."""
    s = track_summary(df)
    cols = ["from_id", "to_id", "gap_s", "dist_m", "cost"]
    s = s[s["role"].isin(PERSON_ROLES)].reset_index(drop=True)
    if len(s) < 2:
        return pd.DataFrame(columns=cols)
    n = len(s)
    t0, t1 = s["t0"].to_numpy(), s["t1"].to_numpy()
    gap = t0[None, :] - t1[:, None]                       # gap[a, b] = inicio de b - fin de a
    px = s["x1"].to_numpy()[:, None] + s["vx1"].to_numpy()[:, None] * np.clip(gap, 0, None)
    py = s["y1"].to_numpy()[:, None] + s["vy1"].to_numpy()[:, None] * np.clip(gap, 0, None)
    pred = np.hypot(px - s["x0"].to_numpy()[None, :], py - s["y0"].to_numpy()[None, :])       # error con velocidad constante
    raw = np.hypot(s["x1"].to_numpy()[:, None] - s["x0"].to_numpy()[None, :], s["y1"].to_numpy()[:, None] - s["y0"].to_numpy()[None, :])
    same = (s["team"].to_numpy()[:, None] == s["team"].to_numpy()[None, :]) & \
           ((s["role"].to_numpy()[:, None] == ROLE_GK) == (s["role"].to_numpy()[None, :] == ROLE_GK)) & \
           ((s["role"].to_numpy()[:, None] == ROLE_REF) == (s["role"].to_numpy()[None, :] == ROLE_REF))
    feasible = same & (gap > -min_overlap_tol_s) & (gap <= max_gap_s) & (raw <= vmax_ms * np.clip(gap, 0.2, None) + 1.5) & (pred <= max_dist_m)
    np.fill_diagonal(feasible, False)
    cost = np.where(feasible, np.minimum(pred, raw) + 0.5 * np.clip(gap, 0, None), 1e6)
    r, c = linear_sum_assignment(cost)
    rows = [{"from_id": int(s["track_id"].iat[a]), "to_id": int(s["track_id"].iat[b]), "gap_s": float(gap[a, b]),
             "dist_m": float(raw[a, b]), "cost": float(cost[a, b])} for a, b in zip(r, c) if cost[a, b] < 1e5]
    return pd.DataFrame(rows, columns=cols).sort_values("cost").reset_index(drop=True)


def apply_links(df: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    """Aplica las uniones: cada cadena a → b → c pasa a llevar el ID de su primera trayectoria."""
    nxt = dict(zip(links["from_id"], links["to_id"]))
    prev = set(nxt.values())
    new_id = {}
    for head in [a for a in nxt if a not in prev]:          # cabezas de cadena
        cur = head
        seen = set()
        while cur is not None and cur not in seen:
            new_id[cur] = head
            seen.add(cur)
            cur = nxt.get(cur)
    out = df.copy()
    out["track_id"] = out["track_id"].map(lambda t: new_id.get(t, t))
    return out


def stitch(df: pd.DataFrame, **kwargs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sugerencias + aplicación en un paso. Devuelve (datos reparados, uniones aplicadas)."""
    links = suggest_links(df, **kwargs)
    return apply_links(df, links), links


# ---------------------------------------------------------------- operaciones manuales
def merge_tracks(df: pd.DataFrame, keep_id: int, drop_id: int, tol_s: float = 0.25) -> pd.DataFrame:
    """Une `drop_id` en `keep_id`. Falla si las dos trayectorias existen a la vez (no pueden ser el mismo jugador)."""
    a, b = df[df["track_id"] == keep_id]["t_seconds"], df[df["track_id"] == drop_id]["t_seconds"]
    if a.empty or b.empty:
        raise ValueError("Alguna de las trayectorias no existe.")
    overlap = min(a.max(), b.max()) - max(a.min(), b.min())
    if overlap > tol_s:
        raise ValueError(f"Las trayectorias coinciden en el tiempo durante {overlap:.1f} s: no pueden ser el mismo jugador.")
    out = df.copy()
    out.loc[out["track_id"] == drop_id, "track_id"] = keep_id
    return out


def split_track(df: pd.DataFrame, track_id: int, t_split: float, new_id: int | None = None) -> tuple[pd.DataFrame, int]:
    """Divide una trayectoria en `t_split`: lo posterior pasa a un ID nuevo (útil cuando el seguidor ha mezclado a dos jugadores)."""
    mask = (df["track_id"] == track_id) & (df["t_seconds"] >= t_split)
    if not mask.any() or not ((df["track_id"] == track_id) & (df["t_seconds"] < t_split)).any():
        raise ValueError("El instante de corte debe quedar dentro de la trayectoria.")
    new_id = int(new_id if new_id is not None else df["track_id"].max() + 1)
    if (df["track_id"] == new_id).any():
        raise ValueError(f"El ID {new_id} ya existe.")
    out = df.copy()
    out.loc[mask, "track_id"] = new_id
    return out, new_id


def set_attrs(df: pd.DataFrame, track_id: int, team: int | None = None, role: int | None = None) -> pd.DataFrame:
    out = df.copy()
    m = out["track_id"] == track_id
    if team is not None:
        out.loc[m, "team"] = int(team)
    if role is not None:
        out.loc[m, "role"] = int(role)
    return out


def delete_track(df: pd.DataFrame, track_id: int) -> pd.DataFrame:
    return df[df["track_id"] != track_id].reset_index(drop=True)


def fragmentation(df: pd.DataFrame, expected_players: int = 22) -> dict:
    """Cuántas trayectorias hay frente a las esperadas, y qué parte del tiempo está en trayectorias largas."""
    s = track_summary(df[df["role"].isin([ROLE_PLAYER, ROLE_GK])])
    if s.empty:
        return {"tracks": 0, "ratio": 0.0, "median_s": 0.0, "share_in_long": 0.0}
    dur = s["t1"] - s["t0"]
    long = dur >= 0.5 * (df["t_seconds"].max() - df["t_seconds"].min())
    return {"tracks": int(len(s)), "ratio": round(len(s) / expected_players, 2), "median_s": round(float(dur.median()), 1),
            "share_in_long": round(float((s["n"] * long).sum() / s["n"].sum()), 2)}
