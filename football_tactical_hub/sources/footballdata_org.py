"""football-data.org: API REST gratuita (token) con 12 competiciones. Límite: 10 peticiones/minuto."""
import os

import pandas as pd
import requests
import streamlit as st

from sources.schema import finalize, season_label

BASE = "https://api.football-data.org/v4"

# código -> (competición, país)
COMPETITIONS = {
    "PL": ("Premier League", "Inglaterra"), "ELC": ("Championship", "Inglaterra"),
    "PD": ("La Liga", "España"), "BL1": ("Bundesliga", "Alemania"), "SA": ("Serie A", "Italia"),
    "FL1": ("Ligue 1", "Francia"), "DED": ("Eredivisie", "Países Bajos"), "PPL": ("Primeira Liga", "Portugal"),
    "BSA": ("Brasileirão Série A", "Brasil"), "CL": ("UEFA Champions League", "Europa"),
    "EC": ("Eurocopa", "Europa"), "WC": ("Copa del Mundo", "Mundial"),
}
SEASONS = [str(y) for y in range(2025, 2013, -1)]  # año de inicio


def get_token() -> str | None:
    try:
        tok = st.secrets.get("FOOTBALL_DATA_API_KEY")
    except Exception:
        tok = None
    return tok or os.environ.get("FOOTBALL_DATA_API_KEY")


def parse(payload: dict, code: str, season: str) -> pd.DataFrame:
    rows = []
    for m in payload.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        ft = (m.get("score") or {}).get("fullTime") or {}
        rows.append(
            {
                "match_id": m["id"], "match_date": m["utcDate"],
                "home_team": (m.get("homeTeam") or {}).get("name"), "away_team": (m.get("awayTeam") or {}).get("name"),
                "home_score": ft.get("home"), "away_score": ft.get("away"),
            }
        )
    comp, country = COMPETITIONS.get(code, (code, ""))
    df = pd.DataFrame(rows, columns=["match_id", "match_date", "home_team", "away_team", "home_score", "away_score"])
    df["competition"], df["season"], df["country"], df["gender"] = comp, season_label(season), country, "Masculino"
    return finalize(df, "football-data.org")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load(code: str, season: str, token: str) -> pd.DataFrame:
    r = requests.get(f"{BASE}/competitions/{code}/matches", params={"season": season},
                     headers={"X-Auth-Token": token}, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("Límite de 10 peticiones por minuto alcanzado. Espera un minuto y reintenta.")
    if r.status_code in (400, 401, 403):
        raise RuntimeError(f"La API rechazó la petición ({r.status_code}): {r.json().get('message', r.text)[:200]}")
    r.raise_for_status()
    return parse(r.json(), code, season)
