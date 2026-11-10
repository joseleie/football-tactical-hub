"""Esquema unificado de partidos para todas las fuentes."""
import numpy as np
import pandas as pd

from normalize import norm_key

UNIFIED = [
    "source", "competition", "season", "country", "gender", "match_id", "match_date",
    "home_team", "away_team", "home_score", "away_score", "home_xg", "away_xg", "home_key", "away_key",
]


def finalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Completa columnas, normaliza fechas y claves de equipo y ordena por fecha."""
    d = df.copy()
    d["source"] = source
    for c in UNIFIED:
        if c not in d.columns:
            d[c] = np.nan
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for c in ("home_score", "away_score", "home_xg", "away_xg"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["home_key"] = d["home_team"].map(norm_key)
    d["away_key"] = d["away_team"].map(norm_key)
    extras = [c for c in d.columns if c not in UNIFIED]
    return d[UNIFIED + extras].sort_values("match_date").reset_index(drop=True)


def season_label(start_year) -> str:
    y = int(start_year)
    return f"{y}/{y + 1}"
