"""Adaptador de los datos abiertos de Metrica Sports (github.com/metrica-sports/sample-data) al contrato del hub.

Son datos REALES de seguimiento (25 Hz) y eventos sincronizados de partidos anonimizados. Coordenadas originales: 0 a 1
en cada eje, (0, 0) arriba a la izquierda, campo de 105 x 68 m. Úsalos de forma responsable (así lo pide su repositorio)
y no los redistribuyas: se descargan de GitHub en el momento de usarlos.

Convenciones del resultado (mismas que `tracks.parquet` del analizador de vídeo):
  - metros; team 0 = local, 1 = visitante, -1 = balón; role 0 jugador, 1 portero, 3 balón; track_id del balón = -1.
  - orientación: en la 2.ª parte se gira el plano 180° para que cada equipo ataque siempre hacia el mismo lado
    (el local, hacia la derecha), de modo que formas, líneas y mapas sean comparables entre partes.
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

BASE = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data/Sample_Game_{g}/Sample_Game_{g}_"
PITCH_L, PITCH_W = 105.0, 68.0
HZ = 25.0
AWAY_OFFSET = 1000  # track_id de los visitantes = 1000 + dorsal, para que no choquen con los del local


def _read_tracking(source, team_name: str, step: int) -> pd.DataFrame:
    """Lee un CSV de seguimiento de Metrica (formato propio con 3 filas de cabecera) y devuelve filas largas en metros."""
    fresh = (lambda: io.StringIO(source.getvalue())) if isinstance(source, io.StringIO) else (lambda: source)
    # Solo se leen las filas necesarias (1 de cada `step`): el CSV completo ocupa 140.000 filas por equipo
    raw = pd.read_csv(fresh(), header=None, skiprows=lambda i: i < 3 or (i - 3) % step != 0, low_memory=False)
    head = pd.read_csv(fresh(), header=None, nrows=3)
    ids = head.iloc[1].tolist()      # fila 2: dorsal de cada jugador (en la columna de la x)
    names = head.iloc[2].tolist()    # fila 3: Player11,,Player1,,... Ball
    raw = raw.reset_index(drop=True)
    period, frame, t = raw[0].astype(int), raw[1].astype(int), raw[2].astype(float)
    rows = []
    c = 3
    while c < len(names) - 1:
        label = str(names[c])
        if label.startswith("Player"):
            pid = int(re.sub(r"\D", "", label))
            rows.append(pd.DataFrame({"period": period, "frame": frame, "t_seconds": t, "key": pid,
                                      "x": raw[c].astype(float), "y": raw[c + 1].astype(float), "kind": "player"}))
        elif label == "Ball":
            rows.append(pd.DataFrame({"period": period, "frame": frame, "t_seconds": t, "key": -1,
                                      "x": raw[c].astype(float), "y": raw[c + 1].astype(float), "kind": "ball"}))
        c += 2
    df = pd.concat(rows, ignore_index=True).dropna(subset=["x", "y"])
    df["team"] = 0 if team_name == "Home" else 1
    return df


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Metros, giro de la 2.ª parte, porteros y columnas del contrato."""
    df = df.copy()
    flip = df["period"] == 2
    df["x"] = np.where(flip, 1 - df["x"], df["x"])
    df["y"] = np.where(flip, 1 - df["y"], df["y"])
    df["x_pitch"], df["y_pitch"] = df["x"] * PITCH_L, df["y"] * PITCH_W
    is_ball = df["kind"] == "ball"
    df["role"] = np.where(is_ball, 3, 0)
    df["team"] = np.where(is_ball, -1, df["team"])
    df["track_id"] = np.where(is_ball, -1, np.where(df["team"] == 1, AWAY_OFFSET + df["key"], df["key"]))
    # Portero: el jugador de cada equipo cuya posición media está más pegada a su propia línea de gol
    pl = df[~is_ball]
    own_goal_x = pl["team"].map({0: 0.0, 1: PITCH_L})
    dist_goal = (pl["x_pitch"] - own_goal_x).abs().groupby([pl["team"], pl["track_id"]]).mean()
    for team in (0, 1):
        gk = dist_goal.loc[team].idxmin()
        df.loc[(~is_ball) & (df["track_id"] == gk), "role"] = 1
    cols = ["frame", "t_seconds", "track_id", "role", "team", "x_pitch", "y_pitch", "period"]
    return df[cols].sort_values(["t_seconds", "track_id"]).reset_index(drop=True)


def parse_tracking(home, away, hz: float = 5.0) -> pd.DataFrame:
    step = max(1, int(round(HZ / hz)))
    h, a = _read_tracking(home, "Home", step), _read_tracking(away, "Away", step)
    a = a[a["kind"] != "ball"]  # el balón viene repetido en los dos archivos: se conserva el del local
    return _finalize(pd.concat([h, a], ignore_index=True))


def parse_events(source) -> pd.DataFrame:
    """Eventos de Metrica en metros (y con el mismo giro de la 2.ª parte). team: 0 local, 1 visitante."""
    e = pd.read_csv(source)
    e = e.rename(columns={"Start Time [s]": "t_start", "End Time [s]": "t_end", "Start X": "x", "Start Y": "y",
                          "End X": "x_end", "End Y": "y_end"})
    e["team"] = e["Team"].map({"Home": 0, "Away": 1})
    for a, b in (("x", "y"), ("x_end", "y_end")):
        flip = e["Period"] == 2
        e[a] = np.where(flip, 1 - e[a], e[a]) * PITCH_L
        e[b] = np.where(flip, 1 - e[b], e[b]) * PITCH_W
    return e[["team", "Type", "Subtype", "Period", "t_start", "t_end", "From", "To", "x", "y", "x_end", "y_end"]]


def load_open_game(game: int = 1, hz: float = 5.0, fetch=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descarga y convierte el partido de muestra `game` (1 o 2). `fetch(url) -> bytes` es inyectable para pruebas."""
    if game not in (1, 2):
        raise ValueError("Solo los partidos 1 y 2 (formato CSV) están soportados.")
    if fetch is None:
        import requests

        def fetch(url):
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            return r.content
    base = BASE.format(g=game)
    import os
    import tempfile

    paths = []

    def to_path(name):
        """Guarda el CSV en un archivo temporal para leerlo por trozos sin duplicar 30 MB de texto en memoria."""
        data = fetch(base + name)
        fh = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        fh.close()
        paths.append(fh.name)
        return fh.name

    try:
        tracks = parse_tracking(to_path("RawTrackingData_Home_Team.csv"), to_path("RawTrackingData_Away_Team.csv"), hz)
        events = parse_events(to_path("RawEventsData.csv"))
    finally:
        for pth in paths:
            os.unlink(pth)
    return tracks, events
