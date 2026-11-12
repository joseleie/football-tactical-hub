import pandas as pd
import streamlit as st

from core import combined_pool, form_string, history_by_key, team_directory
from normalize import norm_key

all_matches = st.session_state["matches_all"]
extra = st.session_state.get("extra_matches")
ICON = {"V": "🟢 V", "E": "🟡 E", "D": "🔴 D"}

st.title("⚔️ Comparador de equipos")
st.markdown("Dos equipos frente a frente con **todas las fuentes cruzadas** (StatsBomb, football-data, Understat…) y su historial directo.")

# El conjunto sin duplicados se calcula una vez por sesión (y de nuevo si se cargan más fuentes)
sig = (len(all_matches), 0 if extra is None else len(extra))
if st.session_state.get("pool_sig") != sig:
    with st.spinner("Cruzando fuentes…"):
        st.session_state["pool"] = combined_pool(all_matches, extra)
        st.session_state["pool_sig"] = sig
pool = st.session_state["pool"]
directory = team_directory(pool)
names = dict(zip(directory["key"], directory["name"]))
counts = dict(zip(directory["key"], directory["partidos"]))
keys = directory["key"].tolist()

cur = norm_key(st.session_state.get("team") or "")
ia = keys.index(cur) if cur in keys else 0
c1, c2 = st.columns(2)
ka = c1.selectbox("Equipo A", keys, index=ia, format_func=lambda k: f"{names[k]} ({counts[k]})", key="cmp_a")
kb = c2.selectbox("Equipo B", keys, index=min(ia + 1, len(keys) - 1), format_func=lambda k: f"{names[k]} ({counts[k]})", key="cmp_b")
if ka == kb:
    st.info("Elige dos equipos distintos.")
    st.stop()

ha, hb = history_by_key(pool, ka), history_by_key(pool, kb)
comps = sorted(set(ha["competition"]) | set(hb["competition"]))
f1, f2 = st.columns([2, 1])
sel_comps = f1.multiselect("Competición", comps, placeholder="Todas", key="cmp_comps")
years = sorted({int(d[:4]) for d in pd.concat([ha["match_date"], hb["match_date"]]) if isinstance(d, str) and d[:4].isdigit()})
y0, y1 = f2.slider("Años", years[0], years[-1], (years[0], years[-1]), key="cmp_years") if len(years) > 1 else (years[0], years[0])


def apply(h):
    if sel_comps:
        h = h[h["competition"].isin(sel_comps)]
    yr = h["match_date"].str[:4].astype(int)
    return h[(yr >= y0) & (yr <= y1)].reset_index(drop=True)


ha, hb = apply(ha), apply(hb)


def summary(h):
    n = len(h)
    if n == 0:
        return {"PJ": 0, "V-E-D": "—", "Goles (F/C)": "—", "Puntos/partido": "—", "Local (pts/partido)": "—", "Visitante (pts/partido)": "—", "Forma": "—"}
    ppg = lambda d: f"{d['puntos'].mean():.2f}" if len(d) else "—"
    return {"PJ": n, "V-E-D": f"{(h['resultado'] == 'V').sum()}-{(h['resultado'] == 'E').sum()}-{(h['resultado'] == 'D').sum()}",
            "Goles (F/C)": f"{h['gf'].sum()} / {h['gc'].sum()}", "Puntos/partido": f"{h['puntos'].mean():.2f}",
            "Local (pts/partido)": ppg(h[h["condicion"] == "Local"]), "Visitante (pts/partido)": ppg(h[h["condicion"] == "Visitante"]),
            "Forma": form_string(h["resultado"].tail(5))}


st.subheader("Rendimiento global")
table = pd.DataFrame({names[ka]: summary(ha), names[kb]: summary(hb)})
st.dataframe(table.astype(str), width="stretch")

# ---------- historial directo ----------
st.subheader("🤝 Enfrentamientos directos")
h2h = ha[ha["rival_key"] == kb].reset_index(drop=True)
if h2h.empty:
    st.info("No hay partidos entre estos dos equipos en los datos cargados con los filtros actuales.")
else:
    k = st.columns(4)
    k[0].metric("Partidos", len(h2h))
    k[1].metric(f"Victorias {names[ka]}", int((h2h["resultado"] == "V").sum()))
    k[2].metric("Empates", int((h2h["resultado"] == "E").sum()))
    k[3].metric(f"Victorias {names[kb]}", int((h2h["resultado"] == "D").sum()))
    st.caption(f"Goles: {names[ka]} {int(h2h['gf'].sum())} – {int(h2h['gc'].sum())} {names[kb]}")
    t = h2h.assign(Resultado=h2h["resultado"].map(ICON), Marcador=h2h["gf"].astype(str) + " - " + h2h["gc"].astype(str))
    show = t[["match_date", "competition", "season", "condicion", "Marcador", "Resultado", "source"]]
    show.columns = ["Fecha", "Competición", "Temporada", f"{names[ka]} juega de", "Marcador (A - B)", "Resultado para A", "Fuente"]
    st.dataframe(show.sort_values("Fecha", ascending=False), hide_index=True, width="stretch")
    st.bar_chart(pd.DataFrame({names[ka]: h2h["gf"].values, names[kb]: h2h["gc"].values}, index=h2h["match_date"].values), height=240)

st.caption("Los partidos repetidos entre fuentes se descartan (mismo cruce con ±1 día de diferencia). Los nombres se unen por clave normalizada.")
