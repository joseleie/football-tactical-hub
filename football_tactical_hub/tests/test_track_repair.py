import numpy as np
import pandas as pd
import pytest

from track_repair import (apply_links, delete_track, fragmentation, merge_tracks, set_attrs, split_track, stitch, suggest_links,
                          track_summary)
from video_analysis import make_demo_tracks, validate_tracks


def _traj(tid, t, x, y, team=0, role=0):
    t = np.asarray(t, float)
    return pd.DataFrame({"frame": (t * 25).astype(int), "t_seconds": t, "track_id": tid, "role": role, "team": team,
                         "x_pitch": x(t) if callable(x) else x, "y_pitch": y(t) if callable(y) else y})


def test_une_un_jugador_partido_en_dos():
    a = _traj(1, np.arange(0, 10, 0.2), lambda t: 20 + 2 * t, 30.0)            # corre a 2 m/s
    b = _traj(2, np.arange(11.0, 20, 0.2), lambda t: 20 + 2 * t, 30.0)         # reaparece 1 s después, donde debía estar
    fixed, links = stitch(pd.concat([a, b]))
    assert links[["from_id", "to_id"]].values.tolist() == [[1, 2]]
    assert fixed["track_id"].nunique() == 1


def test_no_une_si_es_fisicamente_imposible_o_de_otro_equipo():
    a = _traj(1, np.arange(0, 10, 0.2), 20.0, 30.0)
    lejos = _traj(2, np.arange(10.5, 20, 0.2), 80.0, 30.0)                      # 60 m en 0,5 s
    otro_equipo = _traj(3, np.arange(10.5, 20, 0.2), 20.0, 30.0, team=1)
    solapado = _traj(4, np.arange(5, 15, 0.2), 20.0, 30.0)                      # existe a la vez que 1
    assert suggest_links(pd.concat([a, lejos])).empty
    assert suggest_links(pd.concat([a, otro_equipo])).empty
    assert suggest_links(pd.concat([a, solapado])).empty


def test_cada_trayectoria_tiene_un_solo_sucesor():
    a = _traj(1, np.arange(0, 10, 0.2), 20.0, 30.0)
    b = _traj(2, np.arange(10.4, 20, 0.2), 20.5, 30.0)
    c = _traj(3, np.arange(10.4, 20, 0.2), 22.0, 30.0)                          # dos candidatas para continuar a 1
    links = suggest_links(pd.concat([a, b, c]))
    assert len(links) == 1 and links["to_id"].iat[0] == 2                       # gana la más cercana


def test_cadenas_largas_y_portero_y_arbitro_no_se_mezclan():
    parts = [_traj(i, np.arange(i * 10 + 0.4 * i, i * 10 + 9.6, 0.2), lambda t: 10 + 0.5 * t, 20.0) for i in range(1, 5)]
    gk = _traj(9, np.arange(10.4, 19, 0.2), 10 + 0.5 * 10.4, 20.0, role=1)
    fixed, links = stitch(pd.concat(parts + [gk]))
    assert len(links) == 3 and fixed[fixed["track_id"] != 9]["track_id"].nunique() == 1 and (fixed["track_id"] == 9).any()


def test_recupera_los_cortes_de_datos_de_demostracion():
    """Se parte cada jugador en trozos con huecos y se comprueba qué fracción de las uniones verdaderas se recupera."""
    base = validate_tracks(make_demo_tracks(120))
    base = base[base["role"].isin([0, 1])]
    rng = np.random.default_rng(5)
    pieces, truth, nid = [], set(), 1000
    for tid, g in base.groupby("track_id"):
        cuts = np.sort(rng.uniform(15, 105, 3)); last = None; lo = -1
        for hi in list(cuts) + [1e9]:
            seg = g[(g["t_seconds"] > lo) & (g["t_seconds"] <= hi - 0.8)]
            if len(seg) > 3:
                pieces.append(seg.assign(track_id=nid))
                if last is not None:
                    truth.add((last, nid))
                last, nid = nid, nid + 1
            lo = hi
    frag = pd.concat(pieces)
    links = suggest_links(frag)
    found = set(zip(links["from_id"], links["to_id"]))
    recall, precision = len(found & truth) / len(truth), len(found & truth) / max(len(found), 1)
    assert recall >= 0.8 and precision >= 0.8, (recall, precision)
    fixed = apply_links(frag, links)
    assert fragmentation(fixed)["tracks"] < fragmentation(frag)["tracks"]


def test_operaciones_manuales():
    a = _traj(1, np.arange(0, 5, 0.2), 20.0, 30.0)
    b = _traj(2, np.arange(6, 10, 0.2), 25.0, 30.0)
    df = pd.concat([a, b])
    assert merge_tracks(df, 1, 2)["track_id"].nunique() == 1
    with pytest.raises(ValueError, match="coinciden"):
        merge_tracks(pd.concat([a, _traj(3, np.arange(2, 8, 0.2), 20.0, 30.0)]), 1, 3)
    s, new = split_track(merge_tracks(df, 1, 2), 1, 5.5)
    assert new == 2 and s[s["track_id"] == 2]["t_seconds"].min() >= 5.5
    with pytest.raises(ValueError):
        split_track(df, 1, 99.0)
    assert set(set_attrs(df, 1, team=1, role=1).query("track_id == 1")["team"]) == {1}
    assert 2 not in delete_track(df, 2)["track_id"].values
    assert len(track_summary(df)) == 2
