import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from mplsoccer import Pitch

from core import standings
from normalize import match_teams
from sources import apifootball, footballdata_csv, footballdata_org, understat
from sources.schema import UNIFIED

all_matches = st.session_state["matches_all"]

st.title("🔌 Fuentes de datos")
st.markdown(
    "Cada fuente se convierte a un **esquema único de partido** (fecha, equipos, goles, xG, claves de equipo normalizadas). "
    "Lo que cargues aquí se añade al historial de los equipos (cruzado por nombre normalizado)."
)


def add_extra(df: pd.DataFrame):
    cur = st.session_state.get("extra_matches")
    new = pd.concat([cur, df], ignore_index=True) if cur is not None else df
    new = new.drop_duplicates(subset=["source", "competition", "season", "match_id"], keep="last")
    st.session_state["extra_matches"] = new
    st.success(f"Añadidos al catálogo de la sesión. Total de partidos de otras fuentes: {len(new):,}.")


def show_unified(df: pd.DataFrame, key: str):
    """Tabla unificada + clasificación + descarga."""
    if df.empty:
        st.info("Sin partidos.")
        return
    st.caption(f"{len(df):,} partidos · esquema normalizado")
    cols = [c for c in df.columns if c not in ("home_key", "away_key")]
    st.dataframe(df[cols].sort_values("match_date", ascending=False), hide_index=True, width="stretch", height=300)
    groups = df.groupby(["competition", "season"])
    labels = [f"{c} · {s}" for (c, s), _ in groups]
    pick = st.selectbox("Clasificación de…", labels, key=f"{key}_stand")
    comp, season = pick.split(" · ")
    sub = df[(df["competition"] == comp) & (df["season"] == season)]
    table = standings(sub)
    if sub[["home_xg", "away_xg"]].notna().any().any():
        xg = {}
        for t in table["Equipo"]:
            h, a = sub[sub["home_team"] == t], sub[sub["away_team"] == t]
            xg[t] = (h["home_xg"].sum() + a["away_xg"].sum(), h["away_xg"].sum() + a["home_xg"].sum())
        table["xG"] = table["Equipo"].map(lambda t: round(xg[t][0], 1))
        table["xGA"] = table["Equipo"].map(lambda t: round(xg[t][1], 1))
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("⬇️ Descargar CSV normalizado", df.to_csv(index=False).encode("utf-8"), file_name=f"{key}_normalizado.csv", mime="text/csv", key=f"{key}_dl")


tabs = st.tabs(["Understat", "football-data.co.uk", "football-data.org", "API-Football", "🔗 Normalización", "⛔ No integradas"])

# =====================================================================
with tabs[0]:
    st.markdown("**Understat** (vía `soccerdata`): xG por partido, estadísticas de jugador por temporada y tiros de cada partido. 5 grandes ligas.")
    c1, c2 = st.columns(2)
    league = c1.selectbox("Liga", list(understat.LEAGUES.keys()), format_func=lambda k: understat.LEAGUES[k][0] + " (" + understat.LEAGUES[k][1] + ")", key="us_league")
    seasons = c2.multiselect("Temporadas (año de inicio)", understat.SEASONS, default=understat.SEASONS[:1], key="us_seasons")
    if st.button("Cargar Understat", type="primary", key="us_load"):
        frames, errors = [], []
        prog = st.progress(0.0, text="Descargando…")
        for i, s in enumerate(seasons):
            try:
                frames.append(understat.load_schedule(league, s))
            except Exception as e:
                errors.append(f"{s}: {type(e).__name__}: {e}")
            prog.progress((i + 1) / max(len(seasons), 1), text=f"Temporada {s}")
        prog.empty()
        if errors:
            st.error("Algunas temporadas fallaron (bloqueo del sitio o cambio de formato):")
            st.code("\n".join(errors)[:1500])
        if frames:
            st.session_state["us_df"] = (league, pd.concat(frames, ignore_index=True))
    loaded = st.session_state.get("us_df")
    if loaded:
        lg, us = loaded
        t_a, t_b, t_c = st.tabs(["Partidos y xG", "Jugadores (temporada)", "Tiros de un partido"])
        with t_a:
            show_unified(us, "understat")
            if st.button("➕ Añadir al historial de equipos", key="us_add"):
                add_extra(us)
        with t_b:
            seas = sorted(us["season"].unique(), reverse=True)
            ps = st.selectbox("Temporada", seas, key="us_ps")
            start = ps.split("/")[0]
            try:
                players = understat.load_player_season(lg, start)
                st.dataframe(players, hide_index=True, width="stretch", height=400)
            except Exception as e:
                st.error(f"No se pudieron cargar los jugadores: {type(e).__name__}: {e}")
        with t_c:
            seas = sorted(us["season"].unique(), reverse=True)
            ss = st.selectbox("Temporada", seas, key="us_ss")
            sub = us[us["season"] == ss].sort_values("match_date", ascending=False)
            lab = {r.match_id: f"{r.match_date} · {r.home_team} {int(r.home_score)}-{int(r.away_score)} {r.away_team}" for r in sub.itertuples() if pd.notna(r.home_score)}
            gid = st.selectbox("Partido", list(lab.keys()), format_func=lambda k: lab[k], key="us_match")
            if st.button("Ver tiros", key="us_shots"):
                try:
                    shots = understat.load_match_shots(lg, ss.split("/")[0], int(gid))
                    needed = {"location_x", "location_y", "xg"}
                    if not needed.issubset(shots.columns):
                        st.warning(f"Formato inesperado. Columnas: {list(shots.columns)}")
                    else:
                        pitch = Pitch(pitch_type="opta", half=True, pitch_color="grass", line_color="white")
                        fig, ax = pitch.draw(figsize=(9, 7))
                        goal = shots["result"].astype(str).eq("Goal") if "result" in shots.columns else pd.Series(False, index=shots.index)
                        size = 40 + shots["xg"].astype(float) * 600
                        x, y = shots["location_x"].astype(float) * 100, shots["location_y"].astype(float) * 100
                        pitch.scatter(x[~goal], y[~goal], s=size[~goal], ax=ax, color="white", edgecolors="black", alpha=0.7, label="Tiro", zorder=3)
                        pitch.scatter(x[goal], y[goal], s=size[goal], ax=ax, color="red", edgecolors="black", alpha=0.9, label="Gol", zorder=4)
                        ax.legend(loc="lower right", facecolor="black", edgecolor="white", labelcolor="white")
                        st.pyplot(fig)
                        plt.close(fig)
                        st.dataframe(shots, hide_index=True, width="stretch")
                except Exception as e:
                    st.error(f"No se pudieron cargar los tiros: {type(e).__name__}: {e}")

# =====================================================================
with tabs[1]:
    st.markdown(
        "**football-data.co.uk**: CSV gratuitos, sin clave. Resultados desde 1994/95 y, según la liga, tiros, córners, faltas y tarjetas. "
        "Incluye Primeira Liga (Portugal), Serie A/B (Italia), Premier/Championship (Reino Unido) y más."
    )
    c1, c2 = st.columns(2)
    divs = c1.multiselect("Ligas", list(footballdata_csv.LEAGUES.keys()), default=["SP1"],
                          format_func=lambda k: f"{footballdata_csv.LEAGUES[k][0]} ({footballdata_csv.LEAGUES[k][1]})", key="fd_divs")
    seas = c2.multiselect("Temporadas", footballdata_csv.SEASONS, default=footballdata_csv.SEASONS[:2], key="fd_seasons")
    if st.button("Cargar football-data.co.uk", type="primary", key="fd_load"):
        frames, errors = [], []
        jobs = [(d, s) for d in divs for s in seas]
        prog = st.progress(0.0, text="Descargando…")
        for i, (d, s) in enumerate(jobs):
            try:
                frames.append(footballdata_csv.load(d, s))
            except Exception as e:
                errors.append(f"{d} {s}: {type(e).__name__}")
            prog.progress((i + 1) / max(len(jobs), 1))
        prog.empty()
        if errors:
            st.warning(f"{len(errors)} combinaciones no disponibles (la liga no existía esa temporada o el sitio no respondió): " + ", ".join(errors[:12]))
        if frames:
            st.session_state["fd_df"] = pd.concat(frames, ignore_index=True)
    fd = st.session_state.get("fd_df")
    if fd is not None:
        show_unified(fd, "footballdata_co_uk")
        if st.button("➕ Añadir al historial de equipos", key="fd_add"):
            add_extra(fd)

# =====================================================================
with tabs[2]:
    st.markdown("**football-data.org**: API REST gratuita con 12 competiciones (Premier, La Liga, Serie A, Bundesliga, Ligue 1, Primeira Liga, Eredivisie, Championship, Brasileirão, Champions, Eurocopa, Mundial). Límite de 10 peticiones por minuto y marcadores con retraso.")
    token = footballdata_org.get_token()
    if not token:
        st.info("Falta la clave. Regístrate gratis en football-data.org, copia tu token y añádelo en Streamlit Cloud → **Settings → Secrets**:")
        st.code('FOOTBALL_DATA_API_KEY = "tu_token"', language="toml")
    else:
        c1, c2 = st.columns(2)
        code = c1.selectbox("Competición", list(footballdata_org.COMPETITIONS.keys()), format_func=lambda k: footballdata_org.COMPETITIONS[k][0], key="fo_code")
        season = c2.selectbox("Temporada (año de inicio)", footballdata_org.SEASONS, key="fo_season")
        if st.button("Cargar football-data.org", type="primary", key="fo_load"):
            try:
                st.session_state["fo_df"] = footballdata_org.load(code, season, token)
            except Exception as e:
                st.error(str(e))
        fo = st.session_state.get("fo_df")
        if fo is not None:
            show_unified(fo, "footballdata_org")
            if st.button("➕ Añadir al historial de equipos", key="fo_add"):
                add_extra(fo)

# =====================================================================
with tabs[3]:
    st.markdown("**API-Football (API-Sports)**: miles de ligas y copas, también regionales y de divisiones inferiores. El plan gratuito tiene un tope diario de peticiones; cada carga consume al menos una.")
    token = apifootball.get_token()
    if not token:
        st.info("Falta la clave. Créala en api-football.com (plan gratuito) y añádela en **Settings → Secrets**:")
        st.code('API_FOOTBALL_KEY = "tu_clave"', language="toml")
    else:
        q = st.text_input("Buscar liga por nombre", placeholder="Primeira Liga, Serie C, Liga Portugal 2…", key="af_q")
        if q.strip():
            try:
                leagues = apifootball.search_leagues(q.strip(), token)
                st.session_state["af_leagues"] = leagues
            except Exception as e:
                st.error(f"Error de la API: {e}")
        leagues = st.session_state.get("af_leagues")
        if leagues is not None and not leagues.empty:
            lab = {int(r.id): f"{r.liga} · {r.país} ({r.tipo})" for r in leagues.itertuples()}
            lid = st.selectbox("Liga", list(lab.keys()), format_func=lambda k: lab[k], key="af_league")
            years = apifootball.usable_years(leagues[leagues["id"] == lid]["temporadas"].iloc[0])
            if apifootball.plan() == "free":
                st.caption("Plan gratuito: solo temporadas 2022 a 2024. Si tienes un plan de pago, añade `API_FOOTBALL_PLAN = \"pro\"` en Secrets.")
            if not years:
                st.info("Esta liga no tiene temporadas disponibles en tu plan.")
            else:
                year = st.selectbox("Temporada (año de inicio)", years, key="af_year")
                if st.button("Cargar API-Football", type="primary", key="af_load"):
                    try:
                        st.session_state["af_df"] = apifootball.load(lid, str(year), token)
                    except Exception as e:
                        st.error(f"Error de la API: {e}")
        af = st.session_state.get("af_df")
        if af is not None:
            show_unified(af, "apifootball")
            if st.button("➕ Añadir al historial de equipos", key="af_add"):
                add_extra(af)

# =====================================================================
with tabs[4]:
    st.markdown(
        "Los equipos se identifican con una **clave normalizada** (sin tildes ni prefijos tipo FC/CF, con alias como *Inter ↔ Internazionale*) "
        "y una similitud de texto. Aquí ves cómo se emparejan los nombres de las fuentes cargadas con los de StatsBomb."
    )
    extra = st.session_state.get("extra_matches")
    SB_NAMES = {"Bundesliga": "1. Bundesliga"}
    if extra is None or extra.empty:
        st.info("Carga una fuente y pulsa «Añadir al historial de equipos» para ver las equivalencias.")
    else:
        groups = extra.groupby(["source", "competition", "season"]).size().reset_index()[["source", "competition", "season"]]
        labels = [f"{r.source} · {r.competition} · {r.season}" for r in groups.itertuples()]
        pick = st.selectbox("Fuente · competición · temporada", labels, key="norm_pick")
        src, comp, season = pick.split(" · ")
        sub = extra[(extra["source"] == src) & (extra["competition"] == comp) & (extra["season"] == season)]
        names = sorted(set(sub["home_team"]) | set(sub["away_team"]))
        sb_comp = SB_NAMES.get(comp, comp)
        sb_sub = all_matches[(all_matches["competition"] == sb_comp) & (all_matches["season"] == season)]
        if sb_sub.empty:
            st.info(f"StatsBomb no tiene «{sb_comp}» en {season}; se comparan los nombres con TODO el catálogo de StatsBomb.")
            sb_names = sorted(set(all_matches["home_team"]) | set(all_matches["away_team"]))
        else:
            sb_names = sorted(set(sb_sub["home_team"]) | set(sb_sub["away_team"]))
        mapping = match_teams(names, sb_names)
        mapping.columns = [src, "StatsBomb", "Similitud", "Estado"]
        only_bad = st.checkbox("Mostrar solo los que no tienen equivalencia", key="norm_bad")
        st.dataframe(mapping[mapping["Estado"] == "Sin equivalencia"] if only_bad else mapping, hide_index=True, width="stretch")
        ok = (mapping["Estado"] == "Equivalente").mean() * 100
        st.caption(f"{ok:.0f}% de los equipos emparejados automáticamente. Los que no coincidan se resuelven añadiendo un alias en `normalize.py`.")
    st.markdown("**Esquema unificado:** `" + "`, `".join(UNIFIED) + "`")

# =====================================================================
with tabs[5]:
    st.markdown("Fuentes que has propuesto y **no he integrado**, con el motivo y la alternativa que sí está conectada.")
    notint = pd.DataFrame(
        [
            ["Flashscore", "Sin API pública oficial. Los scrapers existentes leen su feed privado y piden revisar sus términos de uso; es frágil y arriesgado.", "Resultados: football-data.co.uk / football-data.org / API-Football"],
            ["Opta / StatsPerform", "Datos corporativos de pago; no hay acceso gratuito para particulares.", "StatsBomb Open Data (eventos) y Understat (xG)"],
            ["TheStatsAPI", "Servicio de pago (con prueba gratuita limitada).", "API-Football (plan gratuito)"],
            ["ZeroZero.pt", "Sin API; solo scraping de una web con derechos propios.", "Primeira Liga en football-data.co.uk (P1) y football-data.org (PPL)"],
            ["Liga Portugal (endpoints de la app)", "Son endpoints privados de su app móvil; usarlos implica ingeniería inversa.", "Idem Portugal"],
            ["FIGC / AIC", "Informes anuales en PDF, no datos estructurados.", "Serie A/B en football-data.co.uk (I1, I2)"],
            ["Panini Digital / Datasport", "Base histórica B2B, sin acceso público.", "—"],
            ["Pagelle (Gazzetta / Corriere)", "Contenido editorial con derechos; scraping no recomendable.", "—"],
            ["Goalserve / Live-Score-API", "Feeds de pago o con prueba.", "API-Football"],
            ["BeSoccer API", "Planes de pago bajo contacto.", "API-Football"],
        ],
        columns=["Fuente", "Por qué no", "Alternativa conectada"],
    )
    st.dataframe(notint, hide_index=True, width="stretch")
