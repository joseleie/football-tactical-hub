import pandas as pd

from core import combined_pool, dedupe_matches, history_by_key, team_directory
from normalize import norm_key


def _m(source, date, home, away, hs=1, as_=0, mid=None):
    return {"source": source, "competition": "La Liga", "season": "2026/2027", "match_id": mid or f"{source}{date}{home}",
            "match_date": date, "home_team": home, "away_team": away, "home_score": hs, "away_score": as_,
            "home_key": norm_key(home), "away_key": norm_key(away)}


def test_dedupe_tolera_un_dia_y_respeta_prioridad():
    df = pd.DataFrame([
        _m("football-data.co.uk", "2026-08-15", "Barcelona", "Betis"),
        _m("football-data.org", "2026-08-16", "FC Barcelona", "Real Betis Balompié"),   # +1 día por huso horario
        _m("Understat", "2026-08-15", "Barcelona", "Betis"),
        _m("football-data.co.uk", "2026-08-20", "Barcelona", "Betis"),                   # otro partido (vuelta)
    ])
    out = dedupe_matches(df, ["home_key", "away_key"])
    assert len(out) == 2 and set(out["source"]) == {"Understat", "football-data.co.uk"}
    assert out[out["match_date"] == "2026-08-15"]["source"].iat[0] == "Understat"  # gana la de mayor prioridad


def test_misma_fuente_no_se_considera_duplicada():
    df = pd.DataFrame([_m("football-data.co.uk", "2026-08-15", "A", "B", mid=1), _m("football-data.co.uk", "2026-08-16", "A", "B", mid=2)])
    assert len(dedupe_matches(df, ["home_key", "away_key"])) == 2


def test_dos_dias_de_diferencia_son_partidos_distintos():
    df = pd.DataFrame([_m("Understat", "2026-08-15", "A", "B"), _m("football-data.org", "2026-08-18", "A", "B")])
    assert len(dedupe_matches(df, ["home_key", "away_key"])) == 2


def test_historial_y_enfrentamientos_directos():
    sb = pd.DataFrame([_m("StatsBomb", "2019-03-02", "Barcelona", "Real Madrid", 1, 0), _m("StatsBomb", "2019-10-26", "Real Madrid", "Barcelona", 0, 0)])
    extra = pd.DataFrame([_m("football-data.org", "2026-10-25", "FC Barcelona", "Real Madrid CF", 2, 1)])
    pool = combined_pool(sb, extra)
    d = team_directory(pool)
    assert len(d) == 2 and d["partidos"].sum() == 6            # 3 partidos x 2 equipos, "FC Barcelona" y "Barcelona" unidos
    h = history_by_key(pool, norm_key("Barcelona"))
    assert h["resultado"].tolist() == ["V", "E", "V"] and h["puntos"].sum() == 7
    vs = h[h["rival_key"] == norm_key("Real Madrid")]
    assert len(vs) == 3 and vs["gf"].sum() == 3 and vs["gc"].sum() == 1
