import os
import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pneuma · Stats Dashboard",
    page_icon="img/icon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── SECRETS & INITIALIZATION ──────────────────────────────────────────────────
try:
    token = st.secrets["GITHUB_TOKEN"]
except Exception:
    token = os.getenv("GITHUB_TOKEN", "")

if not token:
    st.warning("GitHub token not configured. Set it in Streamlit secrets or as an environment variable.")

# ── CUSTOM CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=JetBrains+Mono:wght@300;400&display=swap');

    html, body, [class*="css"] { font-family: 'Syne', sans-serif; }
    .block-container { padding: 3rem 2rem 2rem; max-width: 100%; }

    h1, h2, h3 { font-family: 'Syne', sans-serif !important; font-weight: 800 !important; letter-spacing: -0.02em; }

    .metric-row { display: flex; gap: 12px; margin-bottom: 1.5rem; flex-wrap: wrap; }
    .kpi {
        background: #111114; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px; padding: 1rem 1.25rem; flex: 1; min-width: 130px;
    }
    .kpi-label { font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #6b6b78; margin-bottom: 6px; }
    .kpi-val { font-size: 28px; font-weight: 800; color: #f0f0f4; line-height: 1; }
    .kpi-sub { font-size: 11px; color: #6b6b78; font-family: 'JetBrains Mono', monospace; margin-top: 4px; }

    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        background: transparent; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 6px; padding: 5px 14px;
        font-family: 'Syne', sans-serif; font-weight: 600; font-size: 13px;
        color: #6b6b78;
    }
    .stTabs [aria-selected="true"] {
        background: #18181d !important; color: #f0f0f4 !important;
        border-color: #7c6af7 !important;
    }
    div[data-testid="stMetricValue"] { font-family: 'Syne', sans-serif; font-weight: 800; font-size: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── DB CONNECTION ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        host=st.secrets["DB_HOST"],
        database=st.secrets["DB_NAME"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASS"],
        sslmode="require",
        connect_timeout=10,
    )


def get_live_conn():
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return conn
    except (psycopg2.InterfaceError, psycopg2.OperationalError, psycopg2.DatabaseError):
        get_conn.clear()
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return conn


def get_db_signature():
    conn = get_live_conn()
    with conn.cursor() as curs:
        curs.execute('SELECT COUNT(*), COALESCE(MAX("finishedAt"), NULL) FROM "match"')
        match_count, match_latest = curs.fetchone()
        curs.execute('SELECT COUNT(*) FROM "matchPlayer"')
        player_count = curs.fetchone()[0]
        curs.execute('SELECT COUNT(*) FROM "matchGhost"')
        ghost_count = curs.fetchone()[0]
    return match_count, match_latest, player_count, ghost_count

@st.cache_data(ttl=300)
def load_data(signature):
    conn = get_live_conn()
    matches  = pd.read_sql('SELECT * FROM "match" ORDER BY "finishedAt" DESC', conn)
    players  = pd.read_sql('SELECT * FROM "matchPlayer"', conn)
    ghosts   = pd.read_sql('SELECT * FROM "matchGhost"', conn)

    try:
        player_details = pd.read_sql('SELECT "id" AS "playerId", "player_name" FROM "playerDetails"', conn)
        players = players.merge(player_details, on="playerId", how="left")
    except Exception:
        players["player_name"] = pd.NA

    return matches, players, ghosts

# ── PLOTLY THEME ──────────────────────────────────────────────────────────────
COLORS = ['#7c6af7','#3ecfb2','#f0a84e','#f05a5a','#5ab4f0','#c27cf7','#f0d14e','#78c278']
PLOT_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='JetBrains Mono', color='#6b6b78', size=11),
    margin=dict(l=0, r=0, t=30, b=0),
    colorway=COLORS,
)

def fmt_sec(s):
    s = int(s or 0)
    return f"{s//60}m {s%60}s"


def clean_label(value):
    if pd.isna(value):
        return "Unknown"
    text = str(value).strip()
    return text if text else "Unknown"

# ── LOAD ──────────────────────────────────────────────────────────────────────
try:
    signature = get_db_signature()
    matches, players, ghosts = load_data(signature)
except Exception as e:
    st.error(f"**Database connection failed:** {e}")
    st.stop()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## PNEUMA")
    st.markdown("---")

    maps = ["All maps"] + sorted(matches["selectedMap"].dropna().unique().tolist())
    sel_map = st.selectbox("Map filter", maps)

    regions = ["All regions"] + sorted(matches["region"].dropna().unique().tolist())
    sel_region = st.selectbox("Region filter", regions)

    if sel_map != "All maps":
        matches = matches[matches["selectedMap"] == sel_map]
    if sel_region != "All regions":
        matches = matches[matches["region"] == sel_region]

    players = players[players["matchId"].isin(matches["id"])]
    ghosts  = ghosts[ghosts["matchId"].isin(matches["id"])]

    st.markdown("---")

    refresh_clicked = st.button("🔄 Refresh data huanuana")
    if refresh_clicked:
        st.experimental_rerun()

    st.caption(f"{len(matches)} matches loaded")

# ── TABS ──────────────────────────────────────────────────────────────────────
tab_overview, tab_matches, tab_players, tab_ghosts = st.tabs([
    "Overview", "Match history", "Players", "Ghosts"
])

# ════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════
with tab_overview:
    st.markdown("### Dashboard")

    wins = matches["didWin"].sum()
    total = len(matches)
    avg_len = int(matches["gameLengthSeconds"].mean() or 0)
    total_deaths = int(matches["deaths"].sum())
    unique_players = players["playerId"].nunique()
    survival_rate = int(players["didSurvive"].mean() * 100) if len(players) else 0

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Total matches", total)
    c2.metric("Win rate", f"{int(wins/total*100) if total else 0}%", f"{wins} wins")
    c3.metric("Avg duration", fmt_sec(avg_len))
    c4.metric("Total deaths", total_deaths, f"{total_deaths/max(total,1):.1f}/match")
    c5.metric("Unique players", unique_players)
    c6.metric("Survival rate", f"{survival_rate}%")

    st.markdown("---")

    col_l, col_r = st.columns(2)

    with col_l:
        map_counts = matches["selectedMap"].value_counts().reset_index()
        map_counts.columns = ["Map", "Count"]
        fig = px.pie(map_counts, values="Count", names="Map", title="Maps played",
                     color_discrete_sequence=COLORS, hole=0.55)
        fig.update_layout(**PLOT_LAYOUT)
        fig.update_traces(textinfo="label+percent", textfont_color="white")
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        phase_counts = matches["gameEndPhase"].value_counts().reset_index()
        phase_counts.columns = ["Phase", "Count"]
        fig2 = px.bar(phase_counts, x="Phase", y="Count", title="Game end phase",
                      color="Phase", color_discrete_sequence=COLORS)
        fig2.update_layout(**PLOT_LAYOUT, showlegend=False)
        fig2.update_traces(marker_line_width=0)
        st.plotly_chart(fig2, use_container_width=True)

    # Rolling win rate
    st.markdown("#### Rolling win rate (last 50 matches)")
    recent = matches.sort_values("finishedAt").tail(50).reset_index(drop=True)
    recent["win_int"] = recent["didWin"].astype(int)
    recent["rolling_wr"] = recent["win_int"].expanding().mean() * 100
    recent["match_num"] = range(1, len(recent)+1)
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=recent["match_num"], y=recent["rolling_wr"],
        fill='tozeroy', line=dict(color='#7c6af7', width=2),
        fillcolor='rgba(124,106,247,0.1)', name="Win %"
    ))
    fig3.add_trace(go.Scatter(
        x=recent["match_num"], y=[50]*len(recent),
        line=dict(color='rgba(255,255,255,0.15)', width=1, dash='dash'),
        name="50%", showlegend=False
    ))
    fig3.update_layout(**PLOT_LAYOUT, yaxis=dict(range=[0,100], ticksuffix="%"), xaxis_title="Match #")
    st.plotly_chart(fig3, use_container_width=True)

# ════════════════════════════════════════════════════════
# TAB 2 — MATCH HISTORY
# ════════════════════════════════════════════════════════
with tab_matches:
    st.markdown("### Match history")

    col1, col2 = st.columns([3,1])
    with col2:
        result_filter = st.selectbox("Result", ["All", "Wins only", "Losses only"])

    display_matches = matches.copy()
    if result_filter == "Wins only":
        display_matches = display_matches[display_matches["didWin"]]
    elif result_filter == "Losses only":
        display_matches = display_matches[~display_matches["didWin"]]

    display_matches["Duration"] = display_matches["gameLengthSeconds"].apply(fmt_sec)
    display_matches["Result"] = display_matches["didWin"].map({True: "✅ Win", False: "❌ Loss"})

    show_cols = {
        "id": "ID", "selectedMap": "Map", "region": "Region",
        "playerCount": "Players", "Duration": "Duration",
        "deaths": "Deaths", "ghostParentGuessed": "Ghost",
        "gameEndPhase": "Phase", "Result": "Result"
    }
    out = display_matches[[c for c in show_cols if c in display_matches.columns]].rename(columns=show_cols)
    st.dataframe(out, use_container_width=True, hide_index=True, height=500)

# ════════════════════════════════════════════════════════
# TAB 3 — PLAYERS
# ════════════════════════════════════════════════════════
with tab_players:
    st.markdown("### Player performance")

    player_ids = [pid for pid in players["playerId"].dropna().unique().tolist() if pd.notna(pid)]
    player_labels = {}
    for player_id in player_ids:
        names = players.loc[players["playerId"] == player_id, "player_name"].dropna()
        if not names.empty:
            player_labels[player_id] = f"{names.iloc[0]} ({player_id})"
        else:
            player_labels[player_id] = str(player_id)

    player_ids = sorted(player_ids, key=lambda pid: player_labels[pid].lower())

    if not player_ids:
        st.info("No player data for current filters.")
    else:
        select_options = ["All players"] + player_ids
        sel_player = st.selectbox(
            "Select player",
            options=select_options,
            format_func=lambda pid: "All players" if pid == "All players" else player_labels.get(pid, str(pid)),
        )
        pp = players if sel_player == "All players" else players[players["playerId"] == sel_player]

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Games played", len(pp))
        c2.metric("Survival rate", f"{int(pp['didSurvive'].mean()*100)}%")
        c3.metric("Avg distance", int(pp["distanceTravelled"].mean() or 0))
        c4.metric("Avg time @ 0 sanity", f"{int(pp['timeSpentAtZeroSanity'].mean() or 0)}s")
        c5.metric("Top tool", pp["mostUsedTool"].mode()[0] if len(pp) else "—")

        st.markdown("---")
        col_l, col_r = st.columns(2)

        with col_l:
            time_data = pd.DataFrame({
                "Zone": ["In light", "In dark", "In truck", "Ghost room"],
                "Avg seconds": [
                    pp["timeInLight"].mean(),
                    pp["timeInDark"].mean(),
                    pp["timeInTruck"].mean(),
                    pp["timeInGhostRoom"].mean(),
                ]
            })
            fig = px.bar(time_data, x="Zone", y="Avg seconds", title="Time per zone (avg)",
                         color="Zone", color_discrete_sequence=['#5ab4f0','#534AB7','#3ecfb2','#7c6af7'])
            fig.update_layout(**PLOT_LAYOUT, showlegend=False)
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            ghost_values = pp["ghostGuessed"].dropna()
            ghost_values = ghost_values.astype(str).str.strip()
            ghost_values = ghost_values[ghost_values.ne("") & ~ghost_values.isin(["nan", "none", "null"])]
            ghost_enc = ghost_values.value_counts().reset_index()
            ghost_enc.columns = ["Ghost", "Count"]
            fig2 = px.bar(ghost_enc.head(10), x="Count", y="Ghost", orientation='h',
                          title="Top 10 Most Common Ghost Guesses", color_discrete_sequence=['#7c6af7'])
            fig2.update_layout(**PLOT_LAYOUT, showlegend=False, yaxis={'categoryorder':'total ascending'})
            fig2.update_traces(marker_line_width=0, text=None, textposition='none')
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Favourite camped rooms")
        room_counts = pp["mostCampedRoom"].value_counts().reset_index()
        room_counts.columns = ["Room", "Count"]
        fig3 = px.bar(room_counts.head(10), x="Room", y="Count",
                      color_discrete_sequence=['#3ecfb2'])
        fig3.update_layout(**PLOT_LAYOUT, showlegend=False)
        fig3.update_traces(marker_line_width=0)
        st.plotly_chart(fig3, use_container_width=True)

# ════════════════════════════════════════════════════════
# TAB 4 — GHOSTS
# ════════════════════════════════════════════════════════
with tab_ghosts:
    st.markdown("### Ghost behavior")

    if ghosts.empty:
        st.info("No ghost data for current filters.")
    else:
        ghosts_with_match = ghosts.copy()
        if "matchId" in ghosts_with_match.columns and "id" in matches.columns:
            ghosts_with_match = ghosts_with_match.merge(
                matches[["id", "selectedMap"]].rename(columns={"id": "matchId"}),
                on="matchId",
                how="left",
            )

        ghosts_with_match["name"] = ghosts_with_match["name"].fillna("Unknown")
        ghosts_with_match["selectedMap"] = ghosts_with_match["selectedMap"].fillna("Unknown")
        ghosts_with_match["favouriteRoom"] = (
            ghosts_with_match["favouriteRoom"].apply(clean_label)
        )
        ghosts_with_match["favouriteRoomChanges"] = (
            pd.to_numeric(ghosts_with_match["favouriteRoomChanges"], errors="coerce").fillna(0).astype(int)
        )
        ghosts_with_match["mapInteractions"] = (
            pd.to_numeric(ghosts_with_match["mapInteractions"], errors="coerce").fillna(0).astype(int)
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ghost encounters", len(ghosts_with_match))
        c2.metric("Fav room changes", int(ghosts_with_match["favouriteRoomChanges"].sum()))
        c3.metric("Interaction count", int(ghosts_with_match["mapInteractions"].sum()))
        c4.metric("Avg distance", int(ghosts_with_match["distanceTravelled"].mean() or 0))

        st.markdown("---")
        col_l, col_r = st.columns(2)

        with col_l:
            ghost_stats = ghosts_with_match.groupby("name").agg(
                appearances=("name", "count"),
                avg_hunts=("hunts", "mean"),
                avg_poss=("possessions", "mean"),
                avg_events=("ghostEvents", "mean"),
                avg_dist=("distanceTravelled", "mean"),
            ).reset_index().sort_values("appearances", ascending=False)

            fig = px.bar(ghost_stats.sort_values("avg_hunts"), x="avg_hunts", y="name",
                         orientation='h', title="Avg hunts per ghost type",
                         color_discrete_sequence=['#7c6af7'])
            fig.update_layout(**PLOT_LAYOUT, showlegend=False, yaxis={'categoryorder':'total ascending'})
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            fig2 = px.pie(ghost_stats.head(8), values="appearances", names="name",
                          title="Ghost appearance frequency",
                          color_discrete_sequence=COLORS, hole=0.5)
            fig2.update_layout(**PLOT_LAYOUT)
            fig2.update_traces(textinfo="label+percent", textfont_color="white")
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Interaction and room insights")
        interactions_by_ghost = (
            ghosts_with_match.groupby("name", dropna=False)["mapInteractions"].sum().reset_index(name="Interactions")
            .sort_values("Interactions", ascending=False)
        )
        interactions_by_room = (
            ghosts_with_match.groupby("favouriteRoom", dropna=False)["mapInteractions"].sum().reset_index(name="Interactions")
            .sort_values("Interactions", ascending=False)
        )

        col_a, col_b = st.columns(2)
        with col_a:
            fig3 = px.bar(interactions_by_ghost.head(12), x="Interactions", y="name", orientation='h',
                          title="Interactions per ghost", color_discrete_sequence=['#3ecfb2'])
            fig3.update_layout(**PLOT_LAYOUT, showlegend=False, yaxis={'categoryorder':'total ascending'})
            fig3.update_traces(marker_line_width=0)
            st.plotly_chart(fig3, use_container_width=True)

        with col_b:
            fig4 = px.bar(interactions_by_room.head(12), x="Interactions", y="favouriteRoom", orientation='h',
                          title="Interactions per room", color_discrete_sequence=['#f0a84e'])
            fig4.update_layout(**PLOT_LAYOUT, showlegend=False, yaxis={'categoryorder':'total ascending'})
            fig4.update_traces(marker_line_width=0)
            st.plotly_chart(fig4, use_container_width=True)

        st.markdown("#### Player win rate by ghost favourite room")
        ghost_room_outcomes = ghosts_with_match.merge(
            matches[["id", "didWin"]].rename(columns={"id": "matchId"}),
            on="matchId",
            how="left",
        )
        ghost_room_winrate = (
            ghost_room_outcomes.groupby(["name", "favouriteRoom"], dropna=False)
            .agg(
                matches=("matchId", "count"),
                wins=("didWin", "sum"),
                win_rate=("didWin", "mean"),
            )
            .reset_index()
            .sort_values(["matches", "wins"], ascending=False)
        )
        ghost_room_winrate["win_rate_pct"] = (ghost_room_winrate["win_rate"] * 100).round(1)

        ghost_names = ["All ghosts"] + sorted(ghost_room_winrate["name"].dropna().unique().tolist())
        sel_ghost = st.selectbox("Ghost filter", ghost_names)
        if sel_ghost != "All ghosts":
            ghost_room_winrate = ghost_room_winrate[ghost_room_winrate["name"] == sel_ghost]

        if ghost_room_winrate.empty:
            st.info("No win-rate data available for the selected ghost.")
        else:
            fig5 = px.bar(
                ghost_room_winrate,
                x="favouriteRoom",
                y="win_rate_pct",
                color="name",
                text="win_rate_pct",
                title="Win rate by favourite room",
                color_discrete_sequence=COLORS,
            )
            fig5.update_layout(**PLOT_LAYOUT, showlegend=True, xaxis_title="Favourite room", yaxis_title="Win rate %")
            fig5.update_traces(marker_line_width=0)
            st.plotly_chart(fig5, use_container_width=True)

            st.dataframe(
                ghost_room_winrate[["name", "favouriteRoom", "matches", "wins", "win_rate_pct"]].rename(
                    columns={"name": "Ghost", "favouriteRoom": "Favourite room", "matches": "Matches", "wins": "Wins", "win_rate_pct": "Win rate %"}
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("#### Favourite room breakdown")
        fav_room_breakdown = (
            ghosts_with_match.groupby(["name", "selectedMap", "favouriteRoom"], dropna=False)
            .agg(
                appearances=("id", "count"),
                room_changes=("favouriteRoomChanges", "sum"),
                interactions=("mapInteractions", "sum"),
            )
            .reset_index()
            .sort_values(["appearances", "interactions"], ascending=False)
        )

        col_c, col_d = st.columns(2)
        with col_c:
            st.caption("By ghost")
            st.dataframe(
                fav_room_breakdown[["name", "favouriteRoom", "appearances", "room_changes", "interactions"]]
                .rename(columns={"name": "Ghost", "favouriteRoom": "Favourite room", "appearances": "Appearances", "room_changes": "Room changes", "interactions": "Interactions"}),
                use_container_width=True,
                hide_index=True,
                height=280,
            )

        with col_d:
            st.caption("By map")
            st.dataframe(
                fav_room_breakdown[["selectedMap", "favouriteRoom", "appearances", "room_changes", "interactions"]]
                .rename(columns={"selectedMap": "Map", "favouriteRoom": "Favourite room", "appearances": "Appearances", "room_changes": "Room changes", "interactions": "Interactions"}),
                use_container_width=True,
                hide_index=True,
                height=280,
            )

        st.markdown("#### Ghost stats breakdown")
        display_gs = ghost_stats.copy()
        display_gs.columns = ["Ghost", "Appearances", "Avg hunts", "Avg possessions", "Avg events", "Avg distance"]
        display_gs = display_gs.round(1)

        fav_rooms = (
            ghosts_with_match.groupby("name")["favouriteRoom"]
            .agg(lambda x: x.mode()[0] if len(x) else "—")
            .reset_index()
        )
        fav_rooms.columns = ["Ghost", "Fav room"]
        display_gs = display_gs.merge(fav_rooms, on="Ghost", how="left")

        st.dataframe(display_gs, use_container_width=True, hide_index=True)
