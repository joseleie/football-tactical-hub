import streamlit as st

from core import standings

matches = st.session_state["matches"]

st.title("🏆 Competiciones")
st.caption("Todas las competiciones y temporadas del catálogo (usa los filtros de la barra lateral para acotar).")

if matches.empty:
    st.warning("No hay partidos con estos filtros.")
    st.stop()

cs = (
    matches.groupby(["competition", "season", "country", "gender"])
    .agg(Partidos=("match_id", "size"), Equipos=("home_team", "nunique"))
    .reset_index()
    .sort_values(["competition", "season"], ascending=[True, False])
    .reset_index(drop=True)
)
cs.columns = ["Competición", "Temporada", "País / ámbito", "Género", "Partidos", "Equipos"]
st.markdown(f"**{len(cs)}** competiciones·temporadas · **{len(matches):,}** partidos")
st.caption("Pulsa una fila para ver su clasificación y todos sus partidos.")
sel = st.dataframe(cs, hide_index=True, width="stretch", height=320, on_select="rerun", selection_mode="single-row", key="comp_table")

if not sel.selection.rows:
    st.stop()

row = cs.iloc[sel.selection.rows[0]]
sub = matches[(matches["competition"] == row["Competición"]) & (matches["season"] == row["Temporada"])]
st.subheader(f"{row['Competición']} · {row['Temporada']}")

t1, t2 = st.tabs(["📊 Clasificación", "📅 Partidos"])
with t1:
    table = standings(sub)
    ev = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="comp_stand")
    if ev.selection.rows:
        team = table.iloc[ev.selection.rows[0]]["Equipo"]
        st.session_state["team"], st.session_state["player"] = team, None
        if st.button(f"🛡️ Abrir equipo: {team}", type="primary"):
            st.switch_page("views/equipo.py")
    st.bar_chart(table.set_index("Equipo")[["GF", "GC"]], height=320)
with t2:
    show = sub[["match_date", "home_team", "home_score", "away_score", "away_team"]].copy()
    show.columns = ["Fecha", "Local", "GL", "GV", "Visitante"]
    st.dataframe(show, hide_index=True, width="stretch")
    st.download_button("⬇️ Descargar partidos (CSV normalizado)", sub.to_csv(index=False).encode("utf-8"),
                       file_name=f"{row['Competición']}_{row['Temporada'].replace('/', '-')}.csv".replace(" ", "_"), mime="text/csv")
