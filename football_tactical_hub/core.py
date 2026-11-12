"""Capa de datos y estadísticas compartida por todas las páginas."""
import warnings
from concurrent.futures import ThreadPoolExecutor

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from mplsoccer import Pitch
from statsbombpy import sb

warnings.filterwarnings("ignore")

KEYS = ["match_id", "team", "player"]

KEEP_COLS = [
    "match_id", "index", "period", "minute", "second", "type", "team", "player", "position",
    "location", "pass_end_location", "pass_outcome", "pass_goal_assist", "pass_shot_assist",
    "shot_outcome", "shot_statsbomb_xg", "dribble_outcome", "duel_outcome",
    "tactics", "substitution_replacement",
]

# Métricas de recuento por jugador (se muestran en tablas y comparativas)
COUNT_METRICS = {
    "goles": "Goles",
    "xg": "xG",
    "asistencias": "Asistencias",
    "pases_clave": "Pases clave",
    "pases": "Pases",
    "tiros": "Tiros",
    "conducciones": "Conducciones",
    "regates": "Regates ganados",
    "presiones": "Presiones",
    "recuperaciones": "Recuperaciones",
    "intercepciones": "Intercepciones",
    "duelos_ganados": "Duelos ganados",
}
SUM_COLS = ["minutos", "acciones", "pases_ok"] + list(COUNT_METRICS.keys())


# ---------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def get_competitions():
    return sb.competitions(creds={})


@st.cache_data(show_spinner="Cargando el catálogo completo de StatsBomb (solo la primera vez)...", ttl=86400)
def get_all_matches() -> pd.DataFrame:
    """TODOS los partidos de TODAS las competiciones y temporadas abiertas, en un único esquema."""
    from normalize import norm_key

    comps = get_competitions()
    pairs = comps.drop_duplicates(["competition_id", "season_id"]).to_dict("records")

    def fetch(p):
        try:
            m = sb.matches(competition_id=int(p["competition_id"]), season_id=int(p["season_id"]), creds={})
        except Exception:
            return None
        m = m.copy()
        m["competition"] = p["competition_name"]
        m["season"] = p["season_name"]
        m["country"] = p["country_name"]
        m["gender"] = "Femenino" if str(p.get("competition_gender", "")).lower() == "female" else "Masculino"
        m["competition_id"] = int(p["competition_id"])
        m["season_id"] = int(p["season_id"])
        return m

    with ThreadPoolExecutor(max_workers=8) as ex:
        frames = [f for f in ex.map(fetch, pairs) if f is not None]
    df = pd.concat(frames, ignore_index=True)
    df["source"] = "StatsBomb"
    df["match_id"] = df["match_id"].astype(int)
    df["match_date"] = df["match_date"].astype(str)
    cols = ["source", "competition", "season", "country", "gender", "competition_id", "season_id", "match_id",
            "match_date", "home_team", "away_team", "home_score", "away_score"]
    df = df[cols].sort_values("match_date").reset_index(drop=True)
    df["home_key"] = df["home_team"].map(norm_key)
    df["away_key"] = df["away_team"].map(norm_key)
    return df


@st.cache_data(show_spinner=False)
def get_matches(comp_id: int, season_id: int) -> pd.DataFrame:
    m = sb.matches(competition_id=int(comp_id), season_id=int(season_id), creds={})
    return m.sort_values("match_date").reset_index(drop=True)


def _fetch(match_id: int):
    try:
        ev = sb.events(match_id=int(match_id), creds={})
    except Exception:
        return None
    ev["match_id"] = int(match_id)
    for c in KEEP_COLS:
        if c not in ev.columns:
            ev[c] = np.nan
    return ev[KEEP_COLS]


def _minutes_for_match(g: pd.DataFrame, mid: int) -> list:
    """Minutos jugados por cada jugador de un partido (titulares, cambios y respaldo por eventos)."""
    end = float(g["minute"].max()) if len(g) else 90.0
    spans = {}
    for _, r in g[g["type"] == "Starting XI"].iterrows():
        tac = r["tactics"]
        if isinstance(tac, dict):
            for p in tac.get("lineup", []):
                try:
                    spans[(r["team"], p["player"]["name"])] = [0.0, end]
                except Exception:
                    continue
    subs = g[g["type"] == "Substitution"].sort_values("minute")
    for _, r in subs.iterrows():
        t, m = r["team"], float(r["minute"])
        if (t, r["player"]) in spans:
            spans[(t, r["player"])][1] = m
        rep = r["substitution_replacement"]
        if isinstance(rep, dict):
            rep = rep.get("name")
        if isinstance(rep, str):
            spans[(t, rep)] = [m, end]
    for (t, p), gg in g.dropna(subset=["player"]).groupby(["team", "player"]):
        if (t, p) not in spans:
            spans[(t, p)] = [float(gg["minute"].min()), float(gg["minute"].max())]
    return [(mid, t, p, max(b - a, 0.0)) for (t, p), (a, b) in spans.items()]


@st.cache_data(show_spinner="Cargando eventos de los partidos (la primera vez tarda un poco)...", max_entries=8)
def load_scope(match_ids: tuple):
    """Eventos + minutos jugados de un conjunto de partidos. Devuelve (eventos, minutos)."""
    with ThreadPoolExecutor(max_workers=8) as ex:
        frames = [f for f in ex.map(_fetch, match_ids) if f is not None]
    if not frames:
        return pd.DataFrame(columns=KEEP_COLS), pd.DataFrame(columns=KEYS + ["minutos"])
    ev = pd.concat(frames, ignore_index=True)
    rows = []
    for mid, g in ev.groupby("match_id"):
        rows += _minutes_for_match(g, mid)
    minutes = pd.DataFrame(rows, columns=KEYS + ["minutos"])
    # Se excluyen las tandas de penaltis (periodo 5) para no inflar goles ni xG
    ev = ev[ev["period"] != 5].drop(columns=["tactics", "substitution_replacement"]).reset_index(drop=True)
    return ev, minutes


# ---------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------
def teams_of(matches: pd.DataFrame) -> list:
    return sorted(set(matches["home_team"]) | set(matches["away_team"]))


def team_matches(matches: pd.DataFrame, team: str) -> pd.DataFrame:
    m = matches[(matches["home_team"] == team) | (matches["away_team"] == team)].copy()
    m = m.dropna(subset=["home_score", "away_score"])
    for c, default in (("source", ""), ("competition", ""), ("season", ""), ("home_xg", np.nan), ("away_xg", np.nan)):
        if c not in m.columns:
            m[c] = default
    home = m["home_team"] == team
    m["rival"] = np.where(home, m["away_team"], m["home_team"])
    m["condicion"] = np.where(home, "Local", "Visitante")
    m["gf"] = np.where(home, m["home_score"], m["away_score"]).astype(float).astype(int)
    m["gc"] = np.where(home, m["away_score"], m["home_score"]).astype(float).astype(int)
    m["xgf"] = np.where(home, m["home_xg"], m["away_xg"]).astype(float)
    m["xgc"] = np.where(home, m["away_xg"], m["home_xg"]).astype(float)
    m["resultado"] = np.select([m["gf"] > m["gc"], m["gf"] == m["gc"]], ["V", "E"], "D")
    m["puntos"] = m["resultado"].map({"V": 3, "E": 1, "D": 0})
    m["marcador"] = m["gf"].astype(str) + " - " + m["gc"].astype(str)
    cols = ["source", "competition", "season", "match_id", "match_date", "rival", "condicion", "marcador",
            "gf", "gc", "resultado", "puntos", "xgf", "xgc"]
    return m[cols].sort_values("match_date").reset_index(drop=True)


def standings(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t in teams_of(matches):
        tm = team_matches(matches, t)
        rows.append(
            {
                "Equipo": t, "PJ": len(tm),
                "V": int((tm["resultado"] == "V").sum()), "E": int((tm["resultado"] == "E").sum()),
                "D": int((tm["resultado"] == "D").sum()),
                "GF": int(tm["gf"].sum()), "GC": int(tm["gc"].sum()),
                "DG": int(tm["gf"].sum() - tm["gc"].sum()), "Pts": int(tm["puntos"].sum()),
            }
        )
    df = pd.DataFrame(rows).sort_values(["Pts", "DG", "GF"], ascending=False).reset_index(drop=True)
    df.insert(0, "#", range(1, len(df) + 1))
    return df


def team_match_stats(ev: pd.DataFrame) -> pd.DataFrame:
    t = ev["type"]
    k = ["match_id", "team"]
    shots = t == "Shot"
    df = pd.concat(
        [
            ev[t == "Pass"].groupby(k).size().rename("pases"),
            ev[(t == "Pass") & ev["pass_outcome"].isna()].groupby(k).size().rename("pases_ok"),
            ev[shots].groupby(k).size().rename("tiros"),
            ev[shots].groupby(k)["shot_statsbomb_xg"].sum().rename("xg"),
            ev[t == "Pressure"].groupby(k).size().rename("presiones"),
            ev[t == "Ball Recovery"].groupby(k).size().rename("recuperaciones"),
        ],
        axis=1,
    ).fillna(0)
    return df.reset_index()


def _cnt(e, mask, name):
    return e[mask].groupby(KEYS).size().rename(name)


def player_match_stats(ev: pd.DataFrame, minutes: pd.DataFrame) -> pd.DataFrame:
    e = ev[ev["player"].notna()]
    t = e["type"]
    shot = t == "Shot"
    won = e["duel_outcome"].isin(["Won", "Success", "Success In Play", "Success Out"])
    series = [
        _cnt(e, shot & (e["shot_outcome"] == "Goal"), "goles"),
        e[shot].groupby(KEYS)["shot_statsbomb_xg"].sum().rename("xg"),
        _cnt(e, e["pass_goal_assist"].eq(True), "asistencias"),
        _cnt(e, e["pass_shot_assist"].eq(True) | e["pass_goal_assist"].eq(True), "pases_clave"),
        _cnt(e, t == "Pass", "pases"),
        _cnt(e, (t == "Pass") & e["pass_outcome"].isna(), "pases_ok"),
        _cnt(e, shot, "tiros"),
        _cnt(e, t == "Carry", "conducciones"),
        _cnt(e, (t == "Dribble") & (e["dribble_outcome"] == "Complete"), "regates"),
        _cnt(e, t == "Pressure", "presiones"),
        _cnt(e, t == "Ball Recovery", "recuperaciones"),
        _cnt(e, t == "Interception", "intercepciones"),
        _cnt(e, (t == "Duel") & won, "duelos_ganados"),
        e.groupby(KEYS).size().rename("acciones"),
    ]
    out = pd.concat(series, axis=1).fillna(0).reset_index()
    out = out.merge(minutes, on=KEYS, how="left")
    out["minutos"] = out["minutos"].fillna(0)
    for c in SUM_COLS:
        if c not in out.columns:
            out[c] = 0
    return out


def player_summary(pm: pd.DataFrame) -> pd.DataFrame:
    g = pm.groupby(["team", "player"])
    s = g[SUM_COLS].sum()
    s["partidos"] = g["match_id"].nunique()
    s["pct_pases"] = np.where(s["pases"] > 0, s["pases_ok"] / s["pases"] * 100, np.nan)
    s = s.reset_index()
    for c in COUNT_METRICS:
        s[c + "_90"] = np.where(s["minutos"] > 0, s[c] / s["minutos"] * 90, np.nan)
    return s


def form_string(results) -> str:
    icons = {"V": "🟢", "E": "🟡", "D": "🔴"}
    return " ".join(icons[r] for r in results)


# ---------------------------------------------------------------------
# Selección compartida entre páginas
# ---------------------------------------------------------------------
def require_context():
    ctx = st.session_state.get("ctx")
    if not ctx:
        st.info("Elige una competición en la barra lateral.")
        st.stop()
    return ctx


def select_team(teams: list, key: str, label: str = "Equipo", counts: dict | None = None) -> str:
    cur = st.session_state.get("team")
    idx = teams.index(cur) if cur in teams else 0
    fmt = (lambda t: f"{t} ({counts.get(t, 0)} partidos)") if counts else (lambda t: t)
    sel = st.selectbox(label, teams, index=idx, key=key, format_func=fmt)
    if sel != st.session_state.get("team"):
        st.session_state["player"] = None
    st.session_state["team"] = sel
    return sel


def select_player(players: list, key: str, label: str = "Jugador") -> str:
    cur = st.session_state.get("player")
    idx = players.index(cur) if cur in players else 0
    sel = st.selectbox(label, players, index=idx, key=key)
    st.session_state["player"] = sel
    return sel


# ---------------------------------------------------------------------
# Gráficos de campo
# ---------------------------------------------------------------------
def extract_xy(df: pd.DataFrame) -> pd.DataFrame:
    if "location" not in df.columns or df.empty:
        return pd.DataFrame(columns=["x", "y", "type", "player"])
    d = df.dropna(subset=["location"])
    ok = d["location"].apply(lambda l: isinstance(l, (list, tuple, np.ndarray)) and len(l) >= 2)
    d = d[ok]
    return pd.DataFrame(
        {
            "x": d["location"].apply(lambda l: float(l[0])),
            "y": d["location"].apply(lambda l: float(l[1])),
            "type": d["type"],
            "player": d["player"],
        }
    )


MAP_MODES = ["Dispersión", "Calor por zonas", "Calor suavizado (KDE)"]
EVENT_COLORS = {"Pass": "yellow", "Carry": "cyan", "Pressure": "orange", "Shot": "red", "Ball Recovery": "lime"}


def draw_pitch_map(plot_df: pd.DataFrame, mode: str):
    """Dibuja y muestra el mapa en Streamlit. Necesita al menos unos cuantos puntos."""
    if len(plot_df) < 6:
        st.info("No hay suficientes acciones con coordenadas para este filtro.")
        return
    pitch = Pitch(pitch_type="statsbomb", pitch_color="grass", line_color="white", line_zorder=2)
    fig, ax = pitch.draw(figsize=(10, 7))
    if mode == "Dispersión":
        for ev_type in plot_df["type"].unique():
            sub = plot_df[plot_df["type"] == ev_type]
            pitch.scatter(sub["x"], sub["y"], ax=ax, color=EVENT_COLORS.get(ev_type, "white"),
                          edgecolors="black", s=70, alpha=0.8, label=ev_type, zorder=3)
        ax.legend(loc="upper right", facecolor="black", edgecolor="white", labelcolor="white")
    elif mode == "Calor por zonas":
        bs = pitch.bin_statistic(plot_df["x"], plot_df["y"], statistic="count", bins=(12, 8), normalize=True)
        pitch.heatmap(bs, ax=ax, cmap="hot", alpha=0.75, zorder=3)
    else:
        try:
            pitch.kdeplot(plot_df["x"], plot_df["y"], ax=ax, cmap="hot", levels=50, thresh=0.05,
                          fill=True, alpha=0.65, zorder=3)
        except Exception:
            st.warning("Pocos puntos para el KDE. Mostrando dispersión.")
            pitch.scatter(plot_df["x"], plot_df["y"], ax=ax, color="yellow", s=60, alpha=0.8, zorder=3)
    st.pyplot(fig)
    plt.close(fig)


# ---------------------------------------------------------------------
# Ámbito de estadísticas detalladas (evita cargar miles de partidos de golpe)
# ---------------------------------------------------------------------
MAX_MATCHES = 150
WARN_MATCHES = 60


def scope_selector(tm_all: pd.DataFrame, key: str):
    """Deja elegir competición·temporada y carga los eventos de esos partidos. Devuelve (tm, ev, minutos)."""
    tm_all = tm_all[tm_all["source"] == "StatsBomb"].copy()
    tm_all["scope"] = tm_all["competition"] + " · " + tm_all["season"]
    order = tm_all.groupby("scope")["match_date"].max().sort_values(ascending=False).index.tolist()
    counts = tm_all["scope"].value_counts()
    c1, c2 = st.columns([4, 1])
    sel = c1.multiselect(
        "Ámbito de estadísticas detalladas (competición · temporada)", order, default=order[:1],
        format_func=lambda s: f"{s} ({counts[s]} partidos)", key=key,
    )
    if c2.button("Todas", key=key + "_all", help="Selecciona todas las temporadas disponibles de este equipo"):
        st.session_state[key] = order
        st.rerun()
    if not sel:
        st.info("Elige al menos una competición y temporada.")
        st.stop()
    tm = tm_all[tm_all["scope"].isin(sel)].reset_index(drop=True)
    if len(tm) > MAX_MATCHES:
        st.error(f"Has seleccionado {len(tm)} partidos; el máximo para cargar eventos es {MAX_MATCHES}. Reduce las temporadas.")
        st.stop()
    if len(tm) > WARN_MATCHES and not st.checkbox(f"Cargar {len(tm)} partidos (tardará y usa bastante memoria)", key=key + "_ok"):
        st.warning("Marca la casilla para cargar los eventos de tantos partidos.")
        st.stop()
    ev, minutes = load_scope(tuple(int(i) for i in tm["match_id"]))
    return tm, ev, minutes


def team_matches_by_key(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Partidos de un equipo identificado por su clave normalizada (une nombres distintos entre fuentes)."""
    names = set(df.loc[df["home_key"] == key, "home_team"]) | set(df.loc[df["away_key"] == key, "away_team"])
    frames = [team_matches(df, n) for n in names]
    return pd.concat(frames, ignore_index=True).sort_values("match_date") if frames else pd.DataFrame()


def team_counts(matches: pd.DataFrame) -> dict:
    return pd.concat([matches["home_team"], matches["away_team"]]).value_counts().to_dict()


# ---------------------------------------------------------------------
# Cruce de fuentes: duplicados tolerantes a husos horarios y comparación de equipos
# ---------------------------------------------------------------------
SOURCE_PRIORITY = {"StatsBomb": 0, "Understat": 1, "football-data.org": 2, "API-Football": 3, "football-data.co.uk": 4}


def dedupe_matches(df: pd.DataFrame, key_cols: list, tol_days: int = 1) -> pd.DataFrame:
    """Quita el mismo partido repetido en fuentes distintas: misma clave (equipos, condición...) y fecha con ±tol_days
    de diferencia (husos horarios). Se queda con la fuente de mayor prioridad. Dos filas de la MISMA fuente nunca se
    consideran duplicadas."""
    if df.empty:
        return df
    d = df.copy()
    d["_p"] = d["source"].map(SOURCE_PRIORITY).fillna(9)
    d["_d"] = pd.to_datetime(d["match_date"], errors="coerce")
    d = d.sort_values(["_p", "_d"])
    seen: dict = {}
    keep = []
    tol = pd.Timedelta(days=tol_days)
    for idx, *key, date, src in zip(d.index, *[d[c] for c in key_cols], d["_d"], d["source"]):
        key = tuple(key)
        clash = any(s != src and pd.notna(date) and pd.notna(dt) and abs(date - dt) <= tol for dt, s in seen.get(key, []))
        if not clash:
            keep.append(idx)
        seen.setdefault(key, []).append((date, src))
    return df.loc[sorted(keep)].reset_index(drop=True)


def combined_pool(matches_all: pd.DataFrame, extra: pd.DataFrame | None) -> pd.DataFrame:
    """StatsBomb + las demás fuentes en un único conjunto de partidos, sin duplicados."""
    parts = [matches_all] + ([extra] if extra is not None and len(extra) else [])
    pool = pd.concat(parts, ignore_index=True)
    pool = pool.dropna(subset=["home_score", "away_score", "home_key", "away_key"])
    return dedupe_matches(pool, ["home_key", "away_key"])


def team_directory(pool: pd.DataFrame) -> pd.DataFrame:
    """clave normalizada -> nombre más habitual y nº de partidos. Une las variantes de nombre entre fuentes."""
    names = pd.concat([pool[["home_key", "home_team"]].set_axis(["key", "name"], axis=1),
                       pool[["away_key", "away_team"]].set_axis(["key", "name"], axis=1)])
    out = names.groupby("key").agg(name=("name", lambda s: s.value_counts().index[0]), partidos=("name", "size")).reset_index()
    return out.sort_values("name").reset_index(drop=True)


def history_by_key(pool: pd.DataFrame, key: str) -> pd.DataFrame:
    """Partidos de un equipo (por clave normalizada) desde su propia perspectiva."""
    home, away = pool[pool["home_key"] == key], pool[pool["away_key"] == key]

    def side(df, is_home):
        gf, gc = (df["home_score"], df["away_score"]) if is_home else (df["away_score"], df["home_score"])
        return pd.DataFrame({
            "match_date": df["match_date"], "source": df["source"], "competition": df["competition"], "season": df["season"],
            "rival": df["away_team"] if is_home else df["home_team"], "rival_key": df["away_key"] if is_home else df["home_key"],
            "condicion": "Local" if is_home else "Visitante", "gf": gf.astype(int), "gc": gc.astype(int)})

    h = pd.concat([side(home, True), side(away, False)], ignore_index=True)
    h["resultado"] = np.select([h["gf"] > h["gc"], h["gf"] == h["gc"]], ["V", "E"], "D")
    h["puntos"] = h["resultado"].map({"V": 3, "E": 1, "D": 0})
    return h.sort_values("match_date").reset_index(drop=True)
