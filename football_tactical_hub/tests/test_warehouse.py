import io

import pandas as pd
import pytest

import warehouse
from scripts import ingest
from sources import footballdata_csv as fdc


def _matches(n=3, source="football-data.co.uk"):
    return pd.DataFrame({
        "source": source, "competition": "La Liga", "season": "2026/2027", "match_id": [f"SP1-{i}" for i in range(n)],
        "match_date": [f"2026-08-{10 + i}" for i in range(n)], "home_team": "Barcelona", "away_team": "Betis",
        "home_score": 2, "away_score": 1})


def test_upsert_es_idempotente_y_actualiza(tmp_path):
    path = tmp_path / "m.parquet"
    assert warehouse.upsert_matches(_matches(3), path) == 3
    assert warehouse.upsert_matches(_matches(3), path) == 3  # repetir no duplica
    changed = _matches(2).assign(home_score=5)
    assert warehouse.upsert_matches(changed, path) == 3
    df = warehouse.load_matches(path)
    assert sorted(df[df["match_id"].isin(["SP1-0", "SP1-1"])]["home_score"]) == [5, 5]
    assert df[df["match_id"] == "SP1-2"]["home_score"].iat[0] == 2


def test_ids_numericos_y_de_texto_conviven(tmp_path):
    path = tmp_path / "m.parquet"
    warehouse.upsert_matches(_matches(2), path)
    warehouse.upsert_matches(_matches(2, "football-data.org").assign(match_id=[11, 12]), path)
    assert len(warehouse.load_matches(path)) == 4


def test_lectura_robusta(tmp_path):
    assert warehouse.load_matches(tmp_path / "no_existe.parquet") is None
    bad = tmp_path / "roto.parquet"
    bad.write_bytes(b"no es parquet")
    assert warehouse.load_matches(bad) is None


def test_cobertura(tmp_path):
    cov = warehouse.coverage(_matches(3))
    assert cov.loc[0, "partidos"] == 3 and cov.loc[0, "ultimo"] == "2026-08-12"


def test_ingesta_completa_con_fallos_parciales(tmp_path, monkeypatch):
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nSP1,15/08/2026,Barcelona,Ath Madrid,2,1\nSP1,22/08/2026,Sevilla,Barcelona,0,3\n"

    def fake_read(url):
        if "/SP1.csv" in url or "/E0.csv" in url:
            return pd.read_csv(io.StringIO(csv))
        raise ConnectionError("404")  # el resto de ligas falla: la ingesta debe seguir

    monkeypatch.setattr(fdc, "_read", fake_read)
    fdc.load.clear()
    monkeypatch.setattr(warehouse, "MATCHES", tmp_path / "wh" / "matches.parquet")
    monkeypatch.setattr(warehouse, "META", tmp_path / "wh" / "_meta.json")
    monkeypatch.setattr(warehouse, "BASE", tmp_path / "wh")
    # El módulo ingest usa las funciones con los valores por defecto de ruta, así que se parchean sus referencias
    monkeypatch.setattr(warehouse.upsert_matches, "__defaults__", (warehouse.MATCHES,))
    monkeypatch.setattr(warehouse.write_meta, "__defaults__", (warehouse.META,))
    code = ingest.main(["--seasons", "1", "--skip-org", "--pause", "0"])
    assert code == 0
    df = warehouse.load_matches(warehouse.MATCHES)
    assert set(df["competition"]) == {"La Liga", "Premier League"} and len(df) == 4
    meta = warehouse.read_meta(warehouse.META)
    assert meta["matches_total"] == 4 and any("TypeError" not in e and "ConnectionError" in e for e in meta["errors"])


def test_ingesta_sin_datos_devuelve_error(monkeypatch):
    monkeypatch.setattr(fdc, "_read", lambda url: (_ for _ in ()).throw(ConnectionError("sin red")))
    fdc.load.clear()
    assert ingest.main(["--seasons", "1", "--skip-org", "--pause", "0"]) == 1


def test_alias_propios_desde_csv():
    from normalize import norm_key

    assert norm_key("Sp Lisbon") == norm_key("Sporting CP")


def test_duplicados_entre_fuentes():
    a = _matches(2, "football-data.co.uk").assign(home_key="barcelona", away_key="betis")
    b = _matches(2, "football-data.org").assign(match_id=[1, 2], home_key="barcelona", away_key="betis")
    only_a = _matches(1, "football-data.co.uk").assign(home_key="x", away_key="y", match_date="2026-12-01", match_id="z")
    dup = warehouse.duplicates(pd.concat([a, b, only_a]))
    assert len(dup) == 2 and set(dup["fuentes"]) == {"football-data.co.uk, football-data.org"}


def test_equipos_sin_equivalencia_entre_fuentes():
    ref = pd.DataFrame({"source": "football-data.co.uk", "competition": "La Liga", "season": "2026/2027", "match_id": range(4),
                        "match_date": "2026-08-10", "home_team": ["Barcelona", "Sevilla", "Real Madrid", "Ath Madrid"],
                        "away_team": ["Betis", "Valencia", "Girona", "Getafe"]})
    other = pd.DataFrame({"source": "football-data.org", "competition": "La Liga", "season": "2026/2027", "match_id": [100],
                          "match_date": "2026-08-10", "home_team": ["FC Barcelona"], "away_team": ["Equipo Inexistente Zzz"]})
    # la referencia es la fuente con más partidos (co.uk); "Equipo Inexistente Zzz" no se puede emparejar
    out = warehouse.unmatched_teams(pd.concat([ref, other]))
    assert out["equipo"].tolist() == ["Equipo Inexistente Zzz"] and out["referencia"].iat[0] == "football-data.co.uk"


def test_ingesta_de_understat_opcional(tmp_path, monkeypatch):
    import sources.understat as us

    class Fake:
        def __init__(self, *a): pass
        def read_schedule(self):
            idx = pd.MultiIndex.from_tuples([("l", "2026", "g1")], names=["league", "season", "game"])
            return pd.DataFrame({"game_id": [1], "date": pd.to_datetime(["2026-08-15"]), "home_team": ["Barcelona"], "away_team": ["Betis"],
                                 "home_goals": [2], "away_goals": [0], "home_xg": [1.8], "away_xg": [0.4], "is_result": [True]}, index=idx)

    monkeypatch.setattr(us, "_sd", lambda l, s: Fake())
    us.load_schedule.clear()
    frames, errors = ingest.ingest_understat(1, pause_s=0)
    assert len(frames) == 5 and not errors  # 5 ligas
    monkeypatch.setattr(us, "_sd", lambda l, s: (_ for _ in ()).throw(ConnectionError("bloqueado")))
    us.load_schedule.clear()
    frames, errors = ingest.ingest_understat(1, pause_s=0)
    assert frames == [] and len(errors) == 5  # fallar no rompe la ingesta


def test_alias_de_jugadores():
    from normalize import match_player

    cands = ["Pedro González López", "Gavi"]
    assert match_player("Pedri", cands) == "Pedro González López"
    assert match_player("Lionel Messi", ["Lionel Andrés Messi Cuccittini"]) == "Lionel Andrés Messi Cuccittini"


def test_nombres_oficiales_con_decoraciones():
    from normalize import norm_key

    for a, b in [("Real Betis Balompié", "Betis"), ("FC Barcelona", "Barcelona"), ("Valencia CF", "Valencia"),
                 ("Athletic Club", "Ath Bilbao"), ("Club Atlético de Madrid", "Ath Madrid")]:
        assert norm_key(a) == norm_key(b), (a, b, norm_key(a), norm_key(b))
    assert norm_key("Real Madrid") != norm_key("Real Betis")  # sin falsos positivos por compartir "real"
