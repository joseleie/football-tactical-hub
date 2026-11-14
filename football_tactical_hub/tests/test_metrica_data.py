import io

import numpy as np
import pandas as pd
import pytest

import metrica_data as md
from video_analysis import ROLE_BALL, ROLE_GK, ROLE_PLAYER, possession_proxy, validate_tracks


def _csv(side: str, players: list, rows: list) -> io.StringIO:
    """CSV mínimo con el formato de Metrica: 3 filas de cabecera y dos columnas (x, y) por jugador y para el balón."""
    h1 = ",,," + ",,".join([side] * len(players)) + ",,,"
    h2 = ",,," + ",,".join(str(p) for p in players) + ",,,"
    h3 = "Period,Frame,Time [s]," + ",,".join(f"Player{p}" for p in players) + ",,Ball,"
    return io.StringIO("\n".join([h1, h2, h3] + rows) + "\n")


def _tracking():
    # Local: portero 11 (cerca de x=0) y jugador 1. Visitante: portero 25 (cerca de x=1) y jugador 19.
    home = _csv("Home", [11, 1], ["1,1,0.04,0.02,0.50,0.30,0.40,0.50,0.50", "1,6,0.24,0.02,0.50,0.32,0.41,0.52,0.50",
                                  "2,7,0.28,0.98,0.50,0.70,0.60,0.50,0.50", "2,12,0.48,0.98,0.50,0.71,0.60,0.48,0.50"])
    away = _csv("Away", [25, 19], ["1,1,0.04,0.98,0.50,0.60,0.60,0.50,0.50", "1,6,0.24,0.98,0.50,0.61,0.60,0.52,0.50",
                                   "2,7,0.28,0.02,0.50,0.30,0.40,0.50,0.50", "2,12,0.48,0.02,0.50,0.30,0.40,0.48,0.50"])
    return md.parse_tracking(home, away, hz=25.0)


def test_formato_y_conversion_a_metros():
    t = _tracking()
    first = t[(t["frame"] == 1) & (t["track_id"] == 1)].iloc[0]
    assert first["x_pitch"] == pytest.approx(0.30 * 105) and first["y_pitch"] == pytest.approx(0.40 * 68)
    assert set(t["role"]) == {ROLE_PLAYER, ROLE_GK, ROLE_BALL} and set(t["team"]) == {-1, 0, 1}
    assert t[t["role"] == ROLE_GK].groupby("team")["track_id"].first().to_dict() == {0: 11, 1: 1025}  # visitantes: 1000 + dorsal


def test_el_balon_no_esta_duplicado():
    t = _tracking()
    assert t[t["role"] == ROLE_BALL].groupby("frame").size().max() == 1
    validate_tracks(t)
    possession_proxy(t)  # no debe fallar por balones repetidos (fallo detectado con los datos reales)


def test_segunda_parte_gira_el_plano():
    t = _tracking()
    gk_home = t[(t["track_id"] == 11)]
    # El portero local está en x ≈ 0 en la 1.ª parte (0.02) y, tras el giro, también en la 2.ª (0.98 -> 0.02)
    assert gk_home["x_pitch"].between(0, 5).all()
    gk_away = t[(t["track_id"] == 1025)]
    assert gk_away["x_pitch"].between(100, 105).all()


def test_submuestreo():
    full = _tracking()
    half = md.parse_tracking(_csv("Home", [11, 1], [f"1,{i},{i * 0.04},0.02,0.5,0.3,0.4,0.5,0.5" for i in range(1, 11)]),
                             _csv("Away", [25, 19], [f"1,{i},{i * 0.04},0.98,0.5,0.6,0.6,0.5,0.5" for i in range(1, 11)]), hz=5.0)
    assert half["frame"].nunique() == 2 and full["frame"].nunique() == 4  # 25 Hz -> 5 Hz: 1 de cada 5


def test_eventos_en_metros_y_giro():
    ev = io.StringIO("Team,Type,Subtype,Period,Start Frame,Start Time [s],End Frame,End Time [s],From,To,Start X,Start Y,End X,End Y\n"
                     "Home,PASS,,1,1,0.04,3,0.12,Player11,Player1,0.30,0.40,0.50,0.50\n"
                     "Away,PASS,,2,9,0.36,12,0.48,Player25,Player19,0.20,0.10,0.40,0.30\n")
    e = md.parse_events(ev)
    assert e.loc[0, "x"] == pytest.approx(0.30 * 105) and e.loc[0, "team"] == 0
    assert e.loc[1, "x"] == pytest.approx((1 - 0.20) * 105) and e.loc[1, "y"] == pytest.approx((1 - 0.10) * 68)  # 2.ª parte girada


def test_carga_con_descarga_inyectada():
    files = {"RawTrackingData_Home_Team.csv": "", "RawTrackingData_Away_Team.csv": "", "RawEventsData.csv": ""}
    home = _tracking()  # solo para tener datos válidos de partida
    csv_home = _csv("Home", [11, 1], ["1,1,0.04,0.02,0.5,0.3,0.4,0.5,0.5"]).getvalue()
    csv_away = _csv("Away", [25, 19], ["1,1,0.04,0.98,0.5,0.6,0.6,0.5,0.5"]).getvalue()
    ev = "Team,Type,Subtype,Period,Start Frame,Start Time [s],End Frame,End Time [s],From,To,Start X,Start Y,End X,End Y\nHome,PASS,,1,1,0.04,3,0.12,Player11,Player1,0.3,0.4,0.5,0.5\n"
    data = {"Home_Team": csv_home, "Away_Team": csv_away, "Events": ev}
    pick = lambda url: (csv_home if "Home_Team" in url else csv_away if "Away_Team" in url else ev).encode()
    tracks, events = md.load_open_game(1, hz=25, fetch=pick)
    assert len(tracks) > 0 and len(events) == 1
    with pytest.raises(ValueError):
        md.load_open_game(3, fetch=pick)
