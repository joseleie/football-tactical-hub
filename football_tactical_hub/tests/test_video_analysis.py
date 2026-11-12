import numpy as np
import pandas as pd
import pytest

from video_analysis import (ROLE_BALL, ROLE_PLAYER, convex_hull, make_demo_tracks, player_metrics, polygon_area,
                            possession_proxy, team_shape, validate_tracks)


def _track(tid, team, x, y, fps=10, role=ROLE_PLAYER):
    n = len(x)
    return pd.DataFrame({"frame": np.arange(n) * 3, "t_seconds": np.arange(n) / fps, "track_id": tid, "role": role,
                         "team": team, "x_pitch": x, "y_pitch": y})


def test_distancia_y_velocidad_exactas():
    # Velocidad constante de 5 m/s durante 10 s -> 50 m y 18 km/h
    t = np.arange(101) / 10
    m = player_metrics(_track(1, 0, 10 + 5 * t, np.full(101, 30.0)))
    assert m.loc[0, "distance_m"] == pytest.approx(50, rel=0.02)
    assert m.loc[0, "avg_kmh"] == pytest.approx(18, rel=0.02)
    assert m.loc[0, "sprint_s"] == 0


def test_sprint_y_saltos_imposibles():
    t = np.arange(51) / 10
    fast = _track(2, 1, 10 + 8 * t, np.full(51, 20.0))  # 8 m/s = 28,8 km/h
    assert player_metrics(fast).loc[0, "sprint_s"] > 4
    x = 10 + 2 * t
    x[25:] += 40  # salto de 40 m en un instante (cambio de ID): no debe sumar distancia
    m = player_metrics(_track(3, 0, x, np.full(51, 20.0)))
    assert m.loc[0, "distance_m"] < 20


def test_envolvente_y_area():
    pts = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]])
    hull = convex_hull(pts)
    assert len(hull) == 4 and polygon_area(hull) == pytest.approx(100)


def test_forma_de_equipo():
    df = pd.concat([_track(i, 0, np.full(20, 20.0 + 10 * i), np.full(20, 10.0 + 15 * i)) for i in range(4)])
    s = team_shape(df, 0)
    assert s["length_m"] == pytest.approx(30) and s["width_m"] == pytest.approx(45) and s["centroid"] == pytest.approx((35, 32.5))
    assert team_shape(df, 1)["centroid"] is None


def test_posesion():
    a, b = _track(1, 0, np.full(10, 20.0), np.full(10, 30.0)), _track(2, 1, np.full(10, 80.0), np.full(10, 30.0))
    ball = _track(-1, -1, np.r_[np.full(5, 21.0), np.full(5, 79.0)], np.full(10, 30.0), role=ROLE_BALL)
    p = possession_proxy(pd.concat([a, b, ball]))
    assert p["0"] == pytest.approx(0.5) and p["1"] == pytest.approx(0.5)


def test_validacion():
    with pytest.raises(ValueError, match="Faltan columnas"):
        validate_tracks(pd.DataFrame({"frame": [1]}))
    sin = make_demo_tracks(5).assign(x_pitch=np.nan, y_pitch=np.nan)
    with pytest.raises(ValueError, match="calibrar"):
        validate_tracks(sin)


def test_datos_de_demostracion_son_plausibles():
    df = validate_tracks(make_demo_tracks(60))
    assert df["track_id"].nunique() == 24  # 22 jugadores + árbitro + balón (id -1)
    m = player_metrics(df)
    outfield = m[m["role"] == ROLE_PLAYER]
    assert len(m) == 22 and outfield["max_kmh"].max() < 45
    assert outfield["distance_m"].between(10, 600).all()
    assert team_shape(df, 0)["centroid"][0] < team_shape(df, 1)["centroid"][0] + 60
