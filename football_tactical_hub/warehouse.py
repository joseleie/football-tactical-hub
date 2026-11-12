"""Almacén de datos propio (Parquet): partidos normalizados de todas las fuentes, con carga incremental.

La ingesta nocturna (scripts/ingest.py, ejecutada por GitHub Actions) escribe aquí; la app solo LEE,
así que no depende de límites de peticiones ni de que una web esté disponible durante la visita.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sources.schema import UNIFIED

BASE = Path(__file__).parent / "data" / "warehouse"
MATCHES = BASE / "matches.parquet"
META = BASE / "_meta.json"
KEY = ["source", "competition", "season", "match_id"]


def load_matches(path: Path = MATCHES) -> pd.DataFrame | None:
    """Partidos del almacén, o None si aún no existe o no se puede leer."""
    try:
        return pd.read_parquet(path) if path.exists() else None
    except Exception:
        return None


def upsert_matches(new: pd.DataFrame, path: Path = MATCHES) -> int:
    """Añade o actualiza partidos (clave: fuente + competición + temporada + id). Escritura atómica. Devuelve el total."""
    if new is None or new.empty:
        return len(load_matches(path)) if path.exists() else 0
    path.parent.mkdir(parents=True, exist_ok=True)
    old = load_matches(path)
    new = new.copy()
    new["match_id"] = new["match_id"].astype(str)  # los ids de unas fuentes son números y los de otras, texto
    if old is not None:
        old["match_id"] = old["match_id"].astype(str)
    merged = pd.concat([old, new], ignore_index=True) if old is not None else new
    merged = merged.drop_duplicates(subset=KEY, keep="last").sort_values(["source", "competition", "season", "match_date"])
    tmp = path.with_suffix(".tmp")
    merged.to_parquet(tmp, index=False)
    os.replace(tmp, path)  # el archivo nunca queda a medias
    return len(merged)


def write_meta(info: dict, path: Path = META) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **info}, indent=2))


def read_meta(path: Path = META) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Cobertura por fuente, competición y temporada: nº de partidos y fecha del último."""
    g = df.groupby(["source", "competition", "season"]).agg(partidos=("match_id", "size"), ultimo=("match_date", "max")).reset_index()
    return g.sort_values(["source", "competition", "season"], ascending=[True, True, False]).reset_index(drop=True)


def duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Mismo partido (fecha + equipos normalizados) presente en más de una fuente. Útil para comprobar el cruce."""
    d = df.dropna(subset=["home_key", "away_key"])
    g = d.groupby(["match_date", "home_key", "away_key"]).agg(fuentes=("source", lambda s: ", ".join(sorted(set(s)))), n=("source", "nunique"))
    return g[g["n"] > 1].reset_index().drop(columns="n")


def unmatched_teams(df: pd.DataFrame, cutoff: float = 0.8) -> pd.DataFrame:
    """Equipos que una fuente llama de una forma que no se puede emparejar con la fuente de referencia
    (la que más partidos tiene en esa competición y temporada). Son los candidatos a añadir a data/team_aliases.csv."""
    from normalize import match_teams

    rows = []
    for (comp, season), g in df.groupby(["competition", "season"]):
        if g["source"].nunique() < 2:
            continue
        ref = g["source"].value_counts().index[0]
        ref_names = sorted(set(g.loc[g["source"] == ref, "home_team"]) | set(g.loc[g["source"] == ref, "away_team"]))
        for src in sorted(set(g["source"]) - {ref}):
            names = sorted(set(g.loc[g["source"] == src, "home_team"]) | set(g.loc[g["source"] == src, "away_team"]))
            for r in match_teams(names, ref_names, cutoff).itertuples():
                if r.estado != "Equivalente":
                    rows.append({"competition": comp, "season": season, "fuente": src, "equipo": r.izquierda, "referencia": ref})
    return pd.DataFrame(rows, columns=["competition", "season", "fuente", "equipo", "referencia"])
