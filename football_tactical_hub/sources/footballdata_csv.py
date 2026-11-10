"""football-data.co.uk: CSV gratuitos (sin clave) con resultados, tiros, córners y tarjetas de muchas ligas."""
import io

import pandas as pd
import requests
import streamlit as st

from sources.schema import finalize, season_label

BASE = "https://www.football-data.co.uk/mmz4281/{code}/{div}.csv"

# código -> (competición, país)
LEAGUES = {
    "E0": ("Premier League", "Inglaterra"), "E1": ("Championship", "Inglaterra"),
    "E2": ("League One", "Inglaterra"), "E3": ("League Two", "Inglaterra"), "EC": ("Conference", "Inglaterra"),
    "SC0": ("Scottish Premiership", "Escocia"),
    "D1": ("Bundesliga", "Alemania"), "D2": ("2. Bundesliga", "Alemania"),
    "I1": ("Serie A", "Italia"), "I2": ("Serie B", "Italia"),
    "SP1": ("La Liga", "España"), "SP2": ("La Liga 2", "España"),
    "F1": ("Ligue 1", "Francia"), "F2": ("Ligue 2", "Francia"),
    "N1": ("Eredivisie", "Países Bajos"), "B1": ("Jupiler Pro League", "Bélgica"),
    "P1": ("Primeira Liga", "Portugal"), "T1": ("Süper Lig", "Turquía"), "G1": ("Super League", "Grecia"),
}
SEASONS = [season_label(y) for y in range(2026, 1993, -1)]  # "2025/2026" ... "1994/1995"

EXTRA = {  # columna origen -> nombre unificado
    "HS": "home_shots", "AS": "away_shots", "HST": "home_shots_on_target", "AST": "away_shots_on_target",
    "HC": "home_corners", "AC": "away_corners", "HF": "home_fouls", "AF": "away_fouls",
    "HY": "home_yellow", "AY": "away_yellow", "HR": "home_red", "AR": "away_red",
}


def _code(season: str) -> str:
    y = int(season.split("/")[0])
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def _read(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (football-tactical-hub)"})
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), encoding="latin-1", on_bad_lines="skip")


def parse(raw: pd.DataFrame, div: str, season: str) -> pd.DataFrame:
    needed = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not needed.issubset(raw.columns):
        raise ValueError(f"Formato inesperado en {div} {season}. Columnas: {list(raw.columns)[:15]}")
    d = raw.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]).copy()
    d["match_date"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce")
    comp, country = LEAGUES.get(div, (div, ""))
    out = pd.DataFrame(
        {
            "competition": comp, "season": season, "country": country, "gender": "Masculino",
            "match_id": [f"{div}-{_code(season)}-{i}" for i in range(len(d))],
            "match_date": d["match_date"].values,
            "home_team": d["HomeTeam"].values, "away_team": d["AwayTeam"].values,
            "home_score": d["FTHG"].values, "away_score": d["FTAG"].values,
        }
    )
    for src, dst in EXTRA.items():
        if src in d.columns:
            out[dst] = pd.to_numeric(d[src], errors="coerce").values
    return finalize(out, "football-data.co.uk")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load(div: str, season: str) -> pd.DataFrame:
    url = BASE.format(code=_code(season), div=div)
    return parse(_read(url), div, season)
