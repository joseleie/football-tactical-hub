import numpy as np
import pandas as pd
import pytest

from video_analysis import (ROLE_BALL, ROLE_PLAYER, best_offset_xy, possession_phases, space_control, space_control_series,
                            team_lines, validate_tracks, make_demo_tracks)


def _static(players: list, t=0.0):
    """players: [(team, x, y)] en un instante."""
    return pd.DataFrame([{"frame": 0, "t_seconds": t, "track_id": i, "role": ROLE_PLAYER, "team": tm, "x_pitch": x, "y_pitch": y}
                         for i, (tm, x, y) in enumerate(players)])


def test_voronoi_reparto_simetrico_y_asimetrico():
    a, b, owner = space_control(_static([(0, 26.25, 34), (1, 78.75, 34)]), 0.0)
    assert a == pytest.approx(0.5, abs=0.01) and b == pytest.approx(0.5, abs=0.01) and owner.shape == (68, 105)
    a, b, _ = space_control(_static([(0, 30, 34), (1, 90, 34)]), 0.0)     # frontera en x = 60
    assert a == pytest.approx(60 / 105, abs=0.01)
    assert np.isnan(space_control(_static([(0, 30, 34), (0, 40, 34)]), 0.0)[0])  # con un solo equipo no hay reparto


def test_serie_de_control_del_espacio():
    s = space_control_series(validate_tracks(make_demo_tracks(30)), step_s=5)
    assert len(s) >= 5 and np.allclose(s["equipo_0"] + s["equipo_1"], 1.0)


def test_lineas_del_equipo():
    xs = [10, 20, 22, 24, 26, 40, 50, 60, 70]              # 9 jugadores de campo, ataca hacia la derecha
    df = _static([(0, x, 10 + 6 * i) for i, x in enumerate(xs)])
    ln = team_lines(df, 0, attacks_right=True, k=4)
    assert ln["linea_def_m"].iat[0] == pytest.approx(np.mean([10, 20, 22, 24]))
    assert ln["linea_del_m"].iat[0] == pytest.approx(np.mean([70, 60, 50, 40]))
    assert ln["largo_m"].iat[0] == pytest.approx(60) and ln["ancho_m"].iat[0] == pytest.approx(48)
    # Mismo equipo atacando hacia la izquierda: las distancias a su portería se miden desde x = 105
    inv = team_lines(df, 0, attacks_right=False, k=4)
    assert inv["linea_def_m"].iat[0] == pytest.approx(np.mean([105 - 70, 105 - 60, 105 - 50, 105 - 40]))
    assert team_lines(_static([(0, 10, 10)]), 0)["linea_def_m"].isna().all()        # con pocos jugadores no se calcula


def _scene(owner_by_second: list, step=0.2):
    """Escena sintética: cada segundo el balón está pegado a un jugador del equipo indicado (-1 = libre)."""
    rows = []
    for sec, own in enumerate(owner_by_second):
        for k in range(int(1 / step)):
            t = sec + k * step
            bx = 30 + sec * 2.0
            rows.append({"frame": len(rows), "t_seconds": t, "track_id": -1, "role": ROLE_BALL, "team": -1, "x_pitch": bx, "y_pitch": 34})
            rows.append({"frame": len(rows), "t_seconds": t, "track_id": 1, "role": ROLE_PLAYER, "team": 0,
                         "x_pitch": bx + (0.5 if own == 0 else 30), "y_pitch": 34})
            rows.append({"frame": len(rows), "t_seconds": t, "track_id": 2, "role": ROLE_PLAYER, "team": 1,
                         "x_pitch": bx - (0.5 if own == 1 else 30), "y_pitch": 34})
    return pd.DataFrame(rows)


def test_fases_de_posesion():
    owners = [0] * 10 + [-1] * 1 + [0] * 5 + [1] * 8 + [-1] * 4 + [1] * 1
    ph = possession_phases(_scene(owners), min_s=3.0, max_gap_s=2.0)
    assert ph["equipo"].tolist() == [0, 1]
    first = ph.iloc[0]
    assert first["duracion_s"] == pytest.approx(16, abs=1.5)        # el hueco de 1 s une las dos fases del equipo 0
    assert first["avance_m"] > 20                                   # el balón avanza hacia la portería rival (x creciente)
    assert ph.iloc[1]["avance_m"] < 0 or ph.iloc[1]["avance_m"] == pytest.approx(ph.iloc[1]["balon_x_inicio"] - ph.iloc[1]["balon_x_fin"])


def test_desfase_con_eventos_en_metros():
    tracks = validate_tracks(make_demo_tracks(70))
    g = tracks[(tracks["team"] == 0) & (tracks["role"] == 0)]
    rng = np.random.default_rng(4)
    t_game, px, py = [], [], []
    for t in rng.uniform(15, 50, 50):
        tt = g["t_seconds"].iloc[(g["t_seconds"] - t).abs().argmin()]
        pl = g[g["t_seconds"] == tt].iloc[int(rng.integers(0, 10))]
        t_game.append(tt - 23.0); px.append(pl["x_pitch"]); py.append(pl["y_pitch"])
    off, score, _ = best_offset_xy(tracks, 0, t_game, px, py, search=(-60, 60))
    assert off == pytest.approx(23.0, abs=1.0) and score < 1.0
