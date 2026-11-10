"""Normalización de nombres de equipos y jugadores entre fuentes (StatsBomb, Understat...)."""
import difflib
import re
import unicodedata

import pandas as pd

# Palabras sin valor identificativo que se eliminan al comparar
STOP = {"fc", "cf", "ac", "afc", "sc", "sv", "vfb", "vfl", "tsg", "fsv", "cd", "ud", "rc", "rcd", "ssc", "us", "as", "the", "de", "club"}

# Alias frecuentes entre proveedores (clave normalizada -> forma canónica normalizada)
ALIASES = {
    "man utd": "manchester united", "man united": "manchester united", "manchester utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
    "leicester": "leicester city", "newcastle": "newcastle united", "west brom": "west bromwich albion",
    "west ham": "west ham united", "brighton": "brighton and hove albion", "norwich": "norwich city",
    "leeds": "leeds united", "cardiff": "cardiff city", "swansea": "swansea city", "hull": "hull city",
    "stoke": "stoke city", "sheffield utd": "sheffield united", "huddersfield": "huddersfield town",
    "atletico madrid": "atletico madrid", "atl madrid": "atletico madrid", "ath madrid": "atletico madrid",
    "athletic bilbao": "athletic club", "ath bilbao": "athletic club",
    "real sociedad": "real sociedad", "celta vigo": "celta vigo", "celta de vigo": "celta vigo",
    "alaves": "deportivo alaves", "deportivo la coruna": "deportivo la coruna", "la coruna": "deportivo la coruna",
    "rayo vallecano": "rayo vallecano", "espanyol": "espanyol", "espanol": "espanyol",
    "sporting gijon": "sporting gijon", "real valladolid": "real valladolid", "valladolid": "real valladolid",
    "betis": "real betis", "gladbach": "borussia monchengladbach", "borussia m gladbach": "borussia monchengladbach",
    "borussia monchengladbach": "borussia monchengladbach", "bayern munich": "bayern munchen",
    "bayern": "bayern munchen", "leverkusen": "bayer leverkusen", "dortmund": "borussia dortmund",
    "rasenballsport leipzig": "rb leipzig", "rb leipzig": "rb leipzig", "eintracht frankfurt": "eintracht frankfurt",
    "hertha berlin": "hertha berlin", "hertha bsc": "hertha berlin", "mainz 05": "mainz", "1 fsv mainz 05": "mainz",
    "mainz": "mainz", "fc koln": "koln", "1 fc koln": "koln", "cologne": "koln", "koln": "koln",
    "hoffenheim": "hoffenheim", "tsg hoffenheim": "hoffenheim", "1899 hoffenheim": "hoffenheim",
    "paris saint germain": "paris saint germain", "psg": "paris saint germain", "paris sg": "paris saint germain",
    "marseille": "marseille", "olympique marseille": "marseille", "olympique de marseille": "marseille",
    "lyon": "lyon", "olympique lyonnais": "lyon", "saint etienne": "saint etienne", "st etienne": "saint etienne",
    "inter": "internazionale", "inter milan": "internazionale", "internazionale": "internazionale",
    "ac milan": "milan", "milan": "milan", "roma": "roma", "as roma": "roma", "hellas verona": "verona", "verona": "verona",
    "parma calcio 1913": "parma", "parma": "parma", "spal 2013": "spal", "spal": "spal",
}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _basic(text: str) -> str:
    t = strip_accents(str(text)).lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9 ]+", " ", t.replace("-", " "))
    return re.sub(r"\s+", " ", t).strip()


def norm_key(name) -> str:
    """Clave canónica de un equipo: sin tildes, sin signos, sin prefijos tipo FC/CF y con alias resueltos."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    base = _basic(name)
    if base in ALIASES:
        return ALIASES[base]
    tokens = [t for t in base.split() if t not in STOP]
    key = " ".join(tokens) if tokens else base
    return ALIASES.get(key, key)


def similarity(a: str, b: str) -> float:
    ka, kb = norm_key(a), norm_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    ta, tb = set(ka.split()), set(kb.split())
    contain = 0.92 if (ta <= tb or tb <= ta) and min(len(ta), len(tb)) >= 1 and len(ka) >= 4 and len(kb) >= 4 else 0.0
    return max(difflib.SequenceMatcher(None, ka, kb).ratio(), contain)


def match_teams(left, right, cutoff: float = 0.8) -> pd.DataFrame:
    """Empareja dos listas de nombres de equipo. Devuelve izquierda, derecha, puntuación y estado."""
    right = list(right)
    used, rows = set(), []
    scored = []
    for a in left:
        for b in right:
            scored.append((similarity(a, b), a, b))
    scored.sort(reverse=True)
    pairs = {}
    for s, a, b in scored:
        if s < cutoff:
            break
        if a in pairs or b in used:
            continue
        pairs[a] = (b, s)
        used.add(b)
    for a in left:
        b, s = pairs.get(a, (None, 0.0))
        rows.append({"izquierda": a, "derecha": b, "similitud": round(s, 2), "estado": "Equivalente" if b else "Sin equivalencia"})
    return pd.DataFrame(rows)


def player_key(name) -> str:
    return _basic(name) if name else ""


def match_player(name: str, candidates, cutoff: float = 0.8):
    """Busca un jugador entre candidatos aunque el nombre sea parcial (p. ej. 'Lionel Messi' vs 'Lionel Andrés Messi Cuccittini')."""
    kn = player_key(name)
    if not kn:
        return None
    tn = set(kn.split())
    best, best_s = None, 0.0
    for c in candidates:
        kc = player_key(c)
        tc = set(kc.split())
        if not tc:
            continue
        if kn == kc:
            return c
        short, long_ = (tn, tc) if len(tn) <= len(tc) else (tc, tn)
        s = 0.95 if len(short) >= 2 and short <= long_ else difflib.SequenceMatcher(None, kn, kc).ratio()
        if s > best_s:
            best, best_s = c, s
    return best if best_s >= cutoff else None
