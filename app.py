import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

DAY = 60 * 60 * 24

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pneuma · Stats Dashboard",
    page_icon="img/icon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

# ── ROLLUP LOADERS ────────────────────────────────────────────────────────────
@st.cache_data(ttl=DAY)
def load_filter_options():
    conn = get_live_conn()
    maps = pd.read_sql(
        'SELECT DISTINCT "selectedMap" AS v FROM "match" WHERE "selectedMap" IS NOT NULL ORDER BY 1',
        conn)["v"].tolist()
    regions = pd.read_sql(
        'SELECT DISTINCT "region" AS v FROM "match" WHERE "region" IS NOT NULL ORDER BY 1',
        conn)["v"].tolist()
    return maps, regions


@st.cache_data(ttl=DAY)
def load_overview_rollup():
    conn = get_live_conn()
    return pd.read_sql('''
        SELECT "selectedMap", "region",
               date_trunc('day', "finishedAt")::date AS "day",
               "gameEndPhase",
               COUNT(*)                 AS "matches",
               SUM(("didWin")::int)     AS "wins",
               SUM("gameLengthSeconds") AS "totalSeconds",
               SUM("deaths")            AS "deaths"
        FROM "match"
        GROUP BY "selectedMap", "region",
                 date_trunc('day', "finishedAt")::date, "gameEndPhase"
    ''', conn)


@st.cache_data(ttl=DAY)
def load_overview_player_kpis(sel_map, sel_region):
    # COUNT(DISTINCT) can't be summed out of a rollup, so it's queried per-filter.
    conn = get_live_conn()
    return pd.read_sql('''
        SELECT COUNT(DISTINCT mp."playerId") AS "uniquePlayers",
               AVG((mp."didSurvive")::int)   AS "survivalRate"
        FROM "matchPlayer" mp
        JOIN "match" m ON m."id" = mp."matchId"
        WHERE (%(map)s    IS NULL OR m."selectedMap" = %(map)s)
          AND (%(region)s IS NULL OR m."region"      = %(region)s)
    ''', conn, params={"map": sel_map, "region": sel_region})


@st.cache_data(ttl=DAY)
def load_recent_wins(sel_map, sel_region, limit=50):
    conn = get_live_conn()
    return pd.read_sql('''
        SELECT "finishedAt", ("didWin")::int AS "win"
        FROM "match"
        WHERE (%(map)s    IS NULL OR "selectedMap" = %(map)s)
          AND (%(region)s IS NULL OR "region"      = %(region)s)
        ORDER BY "finishedAt" DESC
        LIMIT %(limit)s
    ''', conn, params={"map": sel_map, "region": sel_region, "limit": limit})


@st.cache_data(ttl=DAY)
def load_match_history(sel_map, sel_region, limit):
    conn = get_live_conn()
    return pd.read_sql('''
        SELECT "id", "selectedMap", "region", "playerCount", "gameLengthSeconds",
               "deaths", "ghostParentGuessed", "gameEndPhase", "didWin"
        FROM "match"
        WHERE (%(map)s    IS NULL OR "selectedMap" = %(map)s)
          AND (%(region)s IS NULL OR "region"      = %(region)s)
        ORDER BY "finishedAt" DESC
        LIMIT %(limit)s
    ''', conn, params={"map": sel_map, "region": sel_region, "limit": limit})


@st.cache_data(ttl=DAY)
def load_player_rollup():
    conn = get_live_conn()
    return pd.read_sql('''
        SELECT mp."playerId", m."selectedMap", m."region",
               COUNT(*)                        AS "games",
               SUM((mp."didSurvive")::int)     AS "survivals",
               SUM(mp."distanceTravelled")     AS "totalDistance",
               SUM(mp."timeSpentAtZeroSanity") AS "totalZeroSanity",
               SUM(mp."timeInLight")           AS "timeInLight",
               SUM(mp."timeInDark")            AS "timeInDark",
               SUM(mp."timeInTruck")           AS "timeInTruck",
               SUM(mp."timeInGhostRoom")       AS "timeInGhostRoom"
        FROM "matchPlayer" mp
        JOIN "match" m ON m."id" = mp."matchId"
        GROUP BY mp."playerId", m."selectedMap", m."region"
    ''', conn)


@st.cache_data(ttl=DAY)
def load_player_categoricals():
    conn = get_live_conn()
    return pd.read_sql('''
        SELECT mp."playerId", m."selectedMap", m."region",
               'tool' AS "dim", mp."mostUsedTool" AS "value", COUNT(*) AS "n"
        FROM "matchPlayer" mp JOIN "match" m ON m."id" = mp."matchId"
        WHERE mp."mostUsedTool" IS NOT NULL
        GROUP BY mp."playerId", m."selectedMap", m."region", mp."mostUsedTool"
        UNION ALL
        SELECT mp."playerId", m."selectedMap", m."region",
               'room', mp."mostCampedRoom", COUNT(*)
        FROM "matchPlayer" mp JOIN "match" m ON m."id" = mp."matchId"
        WHERE mp."mostCampedRoom" IS NOT NULL
        GROUP BY mp."playerId", m."selectedMap", m."region", mp."mostCampedRoom"
        UNION ALL
        SELECT mp."playerId", m."selectedMap", m."region",
               'guess', mp."ghostGuessed", COUNT(*)
        FROM "matchPlayer" mp JOIN "match" m ON m."id" = mp."matchId"
        WHERE mp."ghostGuessed" IS NOT NULL
        GROUP BY mp."playerId", m."selectedMap", m."region", mp."ghostGuessed"
    ''', conn)


@st.cache_data(ttl=DAY)
def load_player_names():
    conn = get_live_conn()
    try:
        return pd.read_sql('SELECT "id" AS "playerId", "player_name" FROM "playerDetails"', conn)
    except Exception:
        return pd.DataFrame(columns=["playerId", "player_name"])


@st.cache_data(ttl=DAY)
def load_ghost_rollup():
    # One ghost row per match, so summing match wins/length over ghost rows is exact.
    conn = get_live_conn()
    return pd.read_sql('''
        SELECT g."name", m."selectedMap", m."region",
               COALESCE(NULLIF(TRIM(g."favouriteRoom"), ''), 'Unknown') AS "favouriteRoom",
               COUNT(*)                      AS "appearances",
               SUM((m."didWin")::int)        AS "wins",
               SUM(m."gameLengthSeconds")    AS "totalMatchSeconds",
               SUM(g."hunts")                AS "hunts",
               SUM(g."possessions")          AS "possessions",
               SUM(g."ghostEvents")          AS "ghostEvents",
               SUM(g."mapInteractions")      AS "mapInteractions",
               SUM(g."favouriteRoomChanges") AS "favouriteRoomChanges",
               SUM(g."distanceTravelled")    AS "distanceTravelled"
        FROM "matchGhost" g
        JOIN "match" m ON m."id" = g."matchId"
        GROUP BY g."name", m."selectedMap", m."region",
                 COALESCE(NULLIF(TRIM(g."favouriteRoom"), ''), 'Unknown')
    ''', conn)

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


def safe_div(num, den):
    return num / den if den else 0


def apply_filters(df, sel_map, sel_region):
    if sel_map is not None:
        df = df[df["selectedMap"] == sel_map]
    if sel_region is not None:
        df = df[df["region"] == sel_region]
    return df

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

with st.sidebar:
    st.markdown("## PNEUMA")
    st.markdown("---")

    # Radio, not st.tabs: st.tabs runs every tab body each rerun, so unopened
    # views would still query. With a radio only the selected view's branch runs.
    view = st.radio("View", ["Overview", "Match history", "Players", "Ghosts"])
    st.markdown("---")

    try:
        map_options, region_options = load_filter_options()
        if st.session_state.last_refresh is None:
            st.session_state.last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        st.error(f"**Database connection failed:** {e}")
        st.stop()

    sel_map_label = st.selectbox("Map filter", ["All maps"] + map_options)
    sel_region_label = st.selectbox("Region filter", ["All regions"] + region_options)
    sel_map = None if sel_map_label == "All maps" else sel_map_label
    sel_region = None if sel_region_label == "All regions" else sel_region_label

    st.markdown("---")

    if st.button("🔄 Refresh data"):
        get_conn.clear()
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.rerun()

    st.caption(f"Data last refreshed: {st.session_state.last_refresh or 'Loading...'}")

# ════════════════════════════════════════════════════════
# OVERVIEW
# ════════════════════════════════════════════════════════
if view == "Overview":
    st.markdown("### Dashboard")

    roll = apply_filters(load_overview_rollup(), sel_map, sel_region)
    total = int(roll["matches"].sum())
    wins = int(roll["wins"].sum())
    total_deaths = int(roll["deaths"].sum())
    avg_len = int(safe_div(roll["totalSeconds"].sum(), total))

    pk = load_overview_player_kpis(sel_map, sel_region)
    unique_players = int(pk["uniquePlayers"].iloc[0] or 0)
    survival_rate = int((pk["survivalRate"].iloc[0] or 0) * 100)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Total matches", total)
    c2.metric("Win rate", f"{int(safe_div(wins, total)*100)}%", f"{wins} wins")
    c3.metric("Avg duration", fmt_sec(avg_len))
    c4.metric("Total deaths", total_deaths, f"{safe_div(total_deaths, total):.1f}/match")
    c5.metric("Unique players", unique_players)
    c6.metric("Survival rate", f"{survival_rate}%")

    st.markdown("---")
    col_l, col_r = st.columns(2)

    with col_l:
        map_counts = roll.groupby("selectedMap")["matches"].sum().reset_index()
        map_counts.columns = ["Map", "Count"]
        fig = px.pie(map_counts, values="Count", names="Map", title="Maps played",
                     color_discrete_sequence=COLORS, hole=0.55)
        fig.update_layout(**PLOT_LAYOUT)
        fig.update_traces(textinfo="label+percent", textfont_color="white")
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        phase_counts = roll.groupby("gameEndPhase")["matches"].sum().reset_index()
        phase_counts.columns = ["Phase", "Count"]
        fig2 = px.bar(phase_counts, x="Phase", y="Count", title="Game end phase",
                      color="Phase", color_discrete_sequence=COLORS)
        fig2.update_layout(**PLOT_LAYOUT, showlegend=False)
        fig2.update_traces(marker_line_width=0)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("#### Rolling win rate (last 50 matches)")
    recent = load_recent_wins(sel_map, sel_region, 50).sort_values("finishedAt").reset_index(drop=True)
    recent["rolling_wr"] = recent["win"].expanding().mean() * 100
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
# MATCH HISTORY
# ════════════════════════════════════════════════════════
elif view == "Match history":
    st.markdown("### Match history")

    col1, col2 = st.columns([3,1])
    with col2:
        result_filter = st.selectbox("Result", ["All", "Wins only", "Losses only"])
        row_limit = st.number_input("Max rows", min_value=50, max_value=20000, value=1000, step=50)

    display_matches = load_match_history(sel_map, sel_region, int(row_limit))
    st.caption(f"Showing the {len(display_matches)} most recent matches for the current filters.")

    if result_filter == "Wins only":
        display_matches = display_matches[display_matches["didWin"]]
    elif result_filter == "Losses only":
        display_matches = display_matches[~display_matches["didWin"]]

    display_matches = display_matches.copy()
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
# PLAYERS
# ════════════════════════════════════════════════════════
elif view == "Players":
    st.markdown("### Player performance")

    prr = apply_filters(load_player_rollup(), sel_map, sel_region)
    pcat = apply_filters(load_player_categoricals(), sel_map, sel_region)
    names = load_player_names()
    name_map = dict(zip(names["playerId"], names["player_name"])) if not names.empty else {}

    player_ids = [pid for pid in prr["playerId"].dropna().unique().tolist()]
    player_labels = {}
    for pid in player_ids:
        nm = name_map.get(pid)
        player_labels[pid] = f"{nm} ({pid})" if (pd.notna(nm) and str(nm).strip()) else str(pid)
    player_ids = sorted(player_ids, key=lambda pid: player_labels[pid].lower())

    if not player_ids:
        st.info("No player data for current filters.")
    else:
        sel_player = st.selectbox(
            "Select player",
            options=["All players"] + player_ids,
            format_func=lambda pid: "All players" if pid == "All players" else player_labels.get(pid, str(pid)),
        )
        pr = prr if sel_player == "All players" else prr[prr["playerId"] == sel_player]
        pc = pcat if sel_player == "All players" else pcat[pcat["playerId"] == sel_player]

        games = int(pr["games"].sum())

        def cat_counts(dim):
            sub = pc[pc["dim"] == dim].groupby("value")["n"].sum()
            sub = sub[~sub.index.astype(str).str.strip().str.lower().isin(["", "nan", "none", "null"])]
            return sub.sort_values(ascending=False)

        tool_counts = cat_counts("tool")
        top_tool = tool_counts.index[0] if len(tool_counts) else "—"

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Games played", games)
        c2.metric("Survival rate", f"{int(safe_div(pr['survivals'].sum(), games)*100)}%")
        c3.metric("Avg distance", int(safe_div(pr["totalDistance"].sum(), games)))
        c4.metric("Avg time @ 0 sanity", f"{int(safe_div(pr['totalZeroSanity'].sum(), games))}s")
        c5.metric("Top tool", top_tool)

        st.markdown("---")
        col_l, col_r = st.columns(2)

        with col_l:
            time_data = pd.DataFrame({
                "Zone": ["In light", "In dark", "In truck", "Ghost room"],
                "Avg seconds": [
                    safe_div(pr["timeInLight"].sum(), games),
                    safe_div(pr["timeInDark"].sum(), games),
                    safe_div(pr["timeInTruck"].sum(), games),
                    safe_div(pr["timeInGhostRoom"].sum(), games),
                ]
            })
            fig = px.bar(time_data, x="Zone", y="Avg seconds", title="Time per zone (avg)",
                         color="Zone", color_discrete_sequence=['#5ab4f0','#534AB7','#3ecfb2','#7c6af7'])
            fig.update_layout(**PLOT_LAYOUT, showlegend=False)
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            ghost_enc = cat_counts("guess").head(10).reset_index()
            ghost_enc.columns = ["Ghost", "Count"]
            fig2 = px.bar(ghost_enc, x="Count", y="Ghost", orientation='h',
                          title="Top 10 Most Common Ghost Guesses", color_discrete_sequence=['#7c6af7'])
            fig2.update_layout(**PLOT_LAYOUT, showlegend=False, yaxis={'categoryorder':'total ascending'})
            fig2.update_traces(marker_line_width=0, text=None, textposition='none')
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Favourite camped rooms")
        room_counts = cat_counts("room").head(10).reset_index()
        room_counts.columns = ["Room", "Count"]
        fig3 = px.bar(room_counts, x="Room", y="Count", color_discrete_sequence=['#3ecfb2'])
        fig3.update_layout(**PLOT_LAYOUT, showlegend=False)
        fig3.update_traces(marker_line_width=0)
        st.plotly_chart(fig3, use_container_width=True)

# ════════════════════════════════════════════════════════
# GHOSTS
# ════════════════════════════════════════════════════════
elif view == "Ghosts":
    st.markdown("### Ghost behavior")

    gr = apply_filters(load_ghost_rollup(), sel_map, sel_region)

    if gr.empty:
        st.info("No ghost data for current filters.")
    else:
        encounters = int(gr["appearances"].sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ghost encounters", encounters)
        c2.metric("Fav room changes", int(gr["favouriteRoomChanges"].sum()))
        c3.metric("Interaction count", int(gr["mapInteractions"].sum()))
        c4.metric("Avg distance", int(safe_div(gr["distanceTravelled"].sum(), encounters)))

        gstat = gr.groupby("name").agg(
            appearances=("appearances", "sum"),
            wins=("wins", "sum"),
            total_secs=("totalMatchSeconds", "sum"),
            hunts=("hunts", "sum"),
            possessions=("possessions", "sum"),
            ghostEvents=("ghostEvents", "sum"),
            distanceTravelled=("distanceTravelled", "sum"),
        ).reset_index()
        gstat["avg_match_length"] = gstat["total_secs"] / gstat["appearances"]
        gstat["avg_hunts"] = gstat["hunts"] / gstat["appearances"]
        gstat["avg_poss"] = gstat["possessions"] / gstat["appearances"]
        gstat["avg_events"] = gstat["ghostEvents"] / gstat["appearances"]
        gstat["avg_dist"] = gstat["distanceTravelled"] / gstat["appearances"]
        gstat = gstat.sort_values("appearances", ascending=False)

        st.markdown("---")
        col_l, col_r = st.columns(2)

        with col_l:
            fig = px.bar(gstat.sort_values("avg_hunts"), x="avg_hunts", y="name",
                         orientation='h', title="Avg hunts per ghost type",
                         color_discrete_sequence=['#7c6af7'])
            fig.update_layout(**PLOT_LAYOUT, showlegend=False, yaxis={'categoryorder':'total ascending'})
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            fig2 = px.pie(gstat.head(8), values="appearances", names="name",
                          title="Ghost appearance frequency",
                          color_discrete_sequence=COLORS, hole=0.5)
            fig2.update_layout(**PLOT_LAYOUT)
            fig2.update_traces(textinfo="label+percent", textfont_color="white")
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Interaction and room insights")
        interactions_by_ghost = (
            gr.groupby("name")["mapInteractions"].sum().reset_index(name="Interactions")
            .sort_values("Interactions", ascending=False)
        )
        interactions_by_room = (
            gr.groupby("favouriteRoom")["mapInteractions"].sum().reset_index(name="Interactions")
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
        ghost_room_winrate = (
            gr.groupby(["name", "favouriteRoom"])
            .agg(matches=("appearances", "sum"), wins=("wins", "sum"))
            .reset_index()
            .sort_values(["matches", "wins"], ascending=False)
        )
        ghost_room_winrate["win_rate_pct"] = (
            ghost_room_winrate["wins"] / ghost_room_winrate["matches"] * 100
        ).round(1)

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
            gr.groupby(["name", "selectedMap", "favouriteRoom"])
            .agg(
                appearances=("appearances", "sum"),
                room_changes=("favouriteRoomChanges", "sum"),
                interactions=("mapInteractions", "sum"),
            )
            .reset_index()
            .sort_values(["appearances", "interactions"], ascending=False)
        )
        st.caption("By ghost")
        st.dataframe(
            fav_room_breakdown[["name", "favouriteRoom", "appearances", "room_changes", "interactions"]]
            .rename(columns={"name": "Ghost", "favouriteRoom": "Favourite room", "appearances": "Appearances", "room_changes": "Room changes", "interactions": "Interactions"}),
            hide_index=True,
            height=280,
        )

        st.markdown("#### Ghost stats breakdown")
        fav_idx = gr.groupby(["name", "favouriteRoom"])["appearances"].sum().reset_index()
        fav_rooms = fav_idx.loc[fav_idx.groupby("name")["appearances"].idxmax(), ["name", "favouriteRoom"]]
        fav_rooms.columns = ["Ghost", "Fav room"]

        display_gs = gstat.copy()
        display_gs["Avg Match Length"] = display_gs["avg_match_length"].apply(fmt_sec)
        display_gs = display_gs.rename(columns={
            "name": "Ghost",
            "appearances": "Appearances",
            "avg_hunts": "Avg hunts",
            "avg_poss": "Avg possessions",
            "avg_events": "Avg events",
            "avg_dist": "Avg distance",
        })
        display_gs = display_gs[["Ghost", "Appearances", "Avg Match Length", "Avg hunts", "Avg possessions", "Avg events", "Avg distance"]].round(1)
        display_gs = display_gs.merge(fav_rooms, on="Ghost", how="left")

        st.dataframe(display_gs, use_container_width=True, hide_index=True)
