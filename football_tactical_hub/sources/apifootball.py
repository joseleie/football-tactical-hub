"""API-Football (API-Sports): miles de ligas. Plan gratuito con tope diario de peticiones (clave requerida)."""
import os

import pandas as pd
import requests
import streamlit as st

from sources.schema import finalize, season_label

BASE = "https://v3.football.api-sports.io"
FINISHED = {"FT", "AET", "PEN"}
FREE_YEARS = {2022, 2023, 2024}  # temporadas accesibles con el plan gratuito


def plan() -> str:
    """'free' por defecto. Con un plan de pago, define API_FOOTBALL_PLAN = "pro" en Secrets."""
    try:
        val = st.secrets.get("API_FOOTBALL_PLAN")
    except Exception:
        val = None
    return str(val or os.environ.get("API_FOOTBALL_PLAN") or "free").lower()


def usable_years(years) -> list:
    ys = sorted({int(y) for y in years}, reverse=True)
    return ys if plan() != "free" else [y for y in ys if y in FREE_YEARS]


def get_token() -> str | None:
    try:
        tok = st.secrets.get("API_FOOTBALL_KEY")
    except Exception:
        tok = None
    return tok or os.environ.get("API_FOOTBALL_KEY")


def _get(path: str, params: dict, token: str) -> dict:
    r = requests.get(f"{BASE}{path}", params=params, headers={"x-apisports-key": token}, timeout=30)
    r.raise_for_status()
    data = r.json()
    errors = data.get("errors")
    if errors:
        msg = errors if isinstance(errors, str) else "; ".join(f"{k}: {v}" for k, v in dict(errors).items())
        raise RuntimeError(msg)
    return data


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def search_leagues(query: str, token: str) -> pd.DataFrame:
    data = _get("/leagues", {"search": query}, token)
    rows = []
    for item in data.get("response", []):
        lg, ct = item.get("league", {}), item.get("country", {})
        seasons = [s["year"] for s in item.get("seasons", [])]
        rows.append({"id": lg.get("id"), "liga": lg.get("name"), "país": ct.get("name"), "tipo": lg.get("type"), "temporadas": seasons})
    return pd.DataFrame(rows)


def parse(payload: dict, season: str) -> pd.DataFrame:
    rows = []
    for it in payload.get("response", []):
        fx, lg, tm, gl = it.get("fixture", {}), it.get("league", {}), it.get("teams", {}), it.get("goals", {})
        if (fx.get("status") or {}).get("short") not in FINISHED:
            continue
        rows.append(
            {
                "match_id": fx.get("id"), "match_date": fx.get("date"), "competition": lg.get("name"),
                "country": lg.get("country"), "home_team": (tm.get("home") or {}).get("name"),
                "away_team": (tm.get("away") or {}).get("name"),
                "home_score": gl.get("home"), "away_score": gl.get("away"),
            }
        )
    df = pd.DataFrame(rows, columns=["match_id", "match_date", "competition", "country", "home_team", "away_team", "home_score", "away_score"])
    df["season"] = season_label(season)
    df["gender"] = "Masculino"
    return finalize(df, "API-Football")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load(league_id: int, season: str, token: str) -> pd.DataFrame:
    return parse(_get("/fixtures", {"league": int(league_id), "season": int(season)}, token), season)
