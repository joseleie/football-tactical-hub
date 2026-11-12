import numpy as np
import pandas as pd
import pytest

from video_analysis import (best_offset, events_video_time, make_demo_tracks, pitch_to_statsbomb, statsbomb_to_pitch,
                            sync_score, validate_tracks, _event_arrays, _team_positions)


def _fabricate_events(tracks, team, offset, attacks_right, n=60, seed=1):
    """Eventos 'de StatsBomb' construidos desde el propio seguimiento, con un desfase conocido."""
    rng = np.random.default_rng(seed)
    g = tracks[(tracks["team"] == team) & (tracks["role"] == 0)]
    rows = []
    for t in rng.uniform(15, 50, n):
        tt = g["t_seconds"].iloc[(g["t_seconds"] - t).abs().argmin()]
        pl = g[g["t_seconds"] == tt].sample(1, random_state=int(t * 100) % 1000).iloc[0]
        x, y = pitch_to_statsbomb(pl["x_pitch"], pl["y_pitch"], attacks_right)
        game = tt - offset
        rows.append({"type": "Pass", "period": 1, "minute": int(game // 60), "second": float(game % 60), "location": [float(x), float(y)]})
    return pd.DataFrame(rows)


def test_conversion_de_coordenadas_ida_y_vuelta():
    for ar in (True, False):
        x, y = statsbomb_to_pitch([0, 60, 120], [0, 40, 80], ar)
        bx, by = pitch_to_statsbomb(x, y, ar)
        assert bx == pytest.approx([0, 60, 120]) and by == pytest.approx([0, 40, 80])
    assert statsbomb_to_pitch(120, 40, True)[0] == pytest.approx(105)   # ataca a la derecha: la portería rival está en x = 105
    assert statsbomb_to_pitch(120, 40, False)[0] == pytest.approx(0)    # ataca a la izquierda: se gira el plano


@pytest.mark.parametrize("team,attacks_right,true_offset", [(0, True, 17.0), (1, False, -9.0), (0, True, 0.0)])
def test_recupera_el_desfase_conocido(team, attacks_right, true_offset):
    tracks = validate_tracks(make_demo_tracks(70))
    ev = _fabricate_events(tracks, team, true_offset, attacks_right)
    off, score, curve = best_offset(tracks, team, ev, attacks_right, search=(-60, 60))
    assert off == pytest.approx(true_offset, abs=1.0)
    assert score < 1.0                       # alineado: casi coinciden con un jugador
    assert curve.loc[true_offset + 30 if true_offset + 30 <= 60 else true_offset - 30] > 3 * score + 1  # desalineado: mucho peor


def test_direccion_equivocada_no_alinea():
    tracks = validate_tracks(make_demo_tracks(70))
    ev = _fabricate_events(tracks, 0, 5.0, True)
    good = best_offset(tracks, 0, ev, True, search=(-30, 30))[1]
    bad = best_offset(tracks, 0, ev, False, search=(-30, 30))[1]
    assert bad > good + 5


def test_segunda_parte_requiere_su_propio_offset():
    ev = pd.DataFrame({"type": "Pass", "period": [1, 2], "minute": [10, 50], "second": [0.0, 0.0], "location": [[10, 10]] * 2})
    only_p1 = events_video_time(ev, 100.0)
    assert len(only_p1) == 1 and only_p1["t_video"].iat[0] == pytest.approx(700.0)
    both = events_video_time(ev, 100.0, offset_p2=4000.0)
    assert both["t_video"].tolist() == pytest.approx([700.0, 4000.0 + 5 * 60])


def test_pocos_eventos_no_dan_puntuacion():
    tracks = validate_tracks(make_demo_tracks(30))
    times, pos = _team_positions(tracks, 0)
    assert sync_score(times, pos, np.array([1.0, 2.0]), np.array([50.0, 50.0]), np.array([30.0, 30.0]), 0.0) == float("inf")
