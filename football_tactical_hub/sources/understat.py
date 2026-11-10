"""Understat (vía soccerdata): xG por partido, estadísticas de jugador por temporada y tiros por partido."""
import pandas as pd
import streamlit as st

from sources.schema import finalize, season_label

LEAGUES = {
    "ESP-La Liga": ("La Liga", "España"),
    "ENG-Premier League": ("Premier League", "Inglaterra"),
    "ITA-Serie A": ("Serie A", "Italia"),
    "GER-Bundesliga": ("Bundesliga", "Alemania"),
    "FRA-Ligue 1": ("Ligue 1", "Francia"),
}
SEASONS = [str(y) for y in range(2025, 2013, -1)]  # año de inicio: 2025 = 2025/2026


def _sd(league: str, season: str):
    import soccerdata as sd

    return sd.Understat(league, season)


def parse_schedule(raw: pd.DataFrame, league: str, season: str) -> pd.DataFrame:
    d = raw.reset_index()
    need = {"home_team", "away_team", "home_goals", "away_goals"}
    if not need.issubset(d.columns):
        raise ValueError(f"Formato inesperado de Understat. Columnas: {list(d.columns)}")
    if "is_result" in d.columns:
        d = d[d["is_result"].astype(bool)]
    comp, country = LEAGUES.get(league, (league, ""))
    out = pd.DataFrame(
        {
            "competition": comp, "season": season_label(season), "country": country, "gender": "Masculino",
            "match_id": d["game_id"] if "game_id" in d.columns else range(len(d)),
            "match_date": d["date"] if "date" in d.columns else pd.NaT,
            "home_team": d["home_team"], "away_team": d["away_team"],
            "home_score": d["home_goals"], "away_score": d["away_goals"],
            "home_xg": d["home_xg"] if "home_xg" in d.columns else float("nan"),
            "away_xg": d["away_xg"] if "away_xg" in d.columns else float("nan"),
        }
    )
    return finalize(out, "Understat")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_schedule(league: str, season: str) -> pd.DataFrame:
    return parse_schedule(_sd(league, season).read_schedule(), league, season)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_player_season(league: str, season: str) -> pd.DataFrame:
    return _sd(league, season).read_player_season_stats().reset_index()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_match_shots(league: str, season: str, game_id: int) -> pd.DataFrame:
    return _sd(league, season).read_shot_events(match_id=int(game_id)).reset_index()
