"""Ingesta de datos al almacén. Uso:  python scripts/ingest.py --seasons 2

- football-data.co.uk: todas las ligas configuradas, las últimas N temporadas (sin clave).
- football-data.org: competiciones gratuitas, temporada en curso (solo si existe FOOTBALL_DATA_API_KEY).
Cada fuente falla de forma independiente: un error en una no impide guardar las demás.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

import warehouse  # noqa: E402
from sources import footballdata_csv, footballdata_org, understat  # noqa: E402

log = logging.getLogger("ingest")


def ingest_football_data_csv(n_seasons: int, pause_s: float = 0.3) -> tuple[list[pd.DataFrame], list[str]]:
    start = int(footballdata_csv.current_season().split("/")[0])
    seasons = [footballdata_csv.season_label(start - i) for i in range(n_seasons)]
    frames, errors = [], []
    for div in footballdata_csv.LEAGUES:
        for season in seasons:
            try:
                df = footballdata_csv.load(div, season)
                if len(df):
                    frames.append(df)
            except Exception as exc:  # liga inexistente esa temporada, red caída...
                errors.append(f"{div} {season}: {type(exc).__name__}")
            time.sleep(pause_s)
    return frames, errors


def ingest_football_data_org(pause_s: float = 7.0) -> tuple[list[pd.DataFrame], list[str]]:
    token = footballdata_org.get_token()
    if not token:
        return [], ["football-data.org: sin clave, se omite"]
    season = footballdata_csv.current_season().split("/")[0]
    frames, errors = [], []
    for code in ("PD", "PL", "SA", "BL1", "FL1", "PPL"):
        try:
            frames.append(footballdata_org.load(code, season, token))
        except Exception as exc:
            errors.append(f"football-data.org {code}: {exc}")
        time.sleep(pause_s)  # límite gratuito: 10 peticiones por minuto
    return frames, errors


def ingest_understat(n_seasons: int, pause_s: float = 2.0) -> tuple[list[pd.DataFrame], list[str]]:
    """xG por partido de las 5 grandes ligas. Es un scraper: puede fallar desde los servidores de GitHub, y no pasa nada."""
    start = int(footballdata_csv.current_season().split("/")[0])
    frames, errors = [], []
    for league in understat.LEAGUES:
        for year in range(start, start - n_seasons, -1):
            try:
                df = understat.load_schedule(league, str(year))
                if len(df):
                    frames.append(df)
            except Exception as exc:
                errors.append(f"Understat {league} {year}: {type(exc).__name__}")
            time.sleep(pause_s)
    return frames, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=2, help="Últimas N temporadas de football-data.co.uk")
    ap.add_argument("--skip-org", action="store_true", help="No consultar football-data.org")
    ap.add_argument("--understat", action="store_true", help="Incluir Understat (xG), opcional")
    ap.add_argument("--pause", type=float, default=0.3)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    frames, errors = ingest_football_data_csv(args.seasons, args.pause)
    if not args.skip_org:
        f2, e2 = ingest_football_data_org()
        frames += f2
        errors += e2
    if args.understat:
        f3, e3 = ingest_understat(args.seasons, args.pause)
        frames += f3
        errors += e3
    if not frames:
        log.error("No se obtuvo ningún dato. Errores: %s", errors[:10])
        return 1
    total = warehouse.upsert_matches(pd.concat(frames, ignore_index=True))
    warehouse.write_meta({"matches_total": total, "fetched_frames": len(frames), "errors": errors[:30]})
    log.info("Almacén actualizado: %d partidos. %d combinaciones sin datos.", total, len(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
