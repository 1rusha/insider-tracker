"""Insider Trading Signal Tracker: Streamlit dashboard.

Run locally:   streamlit run app.py
Reads dashboard/insider_signals.db, which src/analyze.py builds.
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_PATH = Path(__file__).parent / "dashboard" / "insider_signals.db"

ROLE_ORDER = ["CEO", "CFO", "Other officer", "Director", "10% owner", "Other"]
SIZE_ORDER = ["$10K-50K", "$50K-250K", "$250K-1M", "$1M+"]
HORIZONS = {"1 month": "excess_1m", "3 months": "excess_3m", "6 months": "excess_6m"}
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Colors (validated for color-blind separation and contrast in both themes).
# Each series keeps its color when filters change: color follows the entity, not its rank.
PALETTE = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"],
        "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "baseline": "#c3c2b7", "surface": "#ffffff",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"],
        "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "baseline": "#383835", "surface": "#0e1117",
    },
}

st.set_page_config(page_title="Insider Signal Tracker", page_icon=":material/insights:", layout="wide")


# ---------- data ----------

@st.cache_data
def load_data():
    with sqlite3.connect(DB_PATH) as conn:
        signals = pd.read_sql_query("SELECT * FROM signals", conn, parse_dates=["filing_date", "entry_date"])
        paths = pd.read_sql_query("SELECT * FROM event_paths", conn)
        latest = pd.read_sql_query("SELECT * FROM latest_buys", conn, parse_dates=["filing_date"])
        meta = pd.read_sql_query("SELECT * FROM meta", conn).iloc[0]
    for df in (signals, latest):
        df["size_bucket"] = pd.cut(df["dollar_value"], [0, 50_000, 250_000, 1_000_000, np.inf],
                                   labels=SIZE_ORDER, right=False).astype(str)
        df["plan"] = df["is_10b5_1_plan"].map({1: "10b5-1 plan", 0: "Discretionary"}).fillna("Not reported")
    signals["buy_type"] = np.where(signals["insiders_last_30d"] >= 3, "Cluster (3+ insiders)", "Solo or pair")
    return signals, paths, latest, meta


def sec_link(cik, accession) -> str | None:
    try:
        return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"
    except (TypeError, ValueError, AttributeError):
        return None


def pct(x: float, signed: bool = True) -> str:
    if pd.isna(x):
        return "n/a"
    return f"{x * 100:+.1f}%" if signed else f"{x * 100:.1f}%"


def summarize(df: pd.DataFrame, by: str, col: str, order: list[str]) -> pd.DataFrame:
    d = df.dropna(subset=[col])
    out = d.groupby(by)[col].agg(avg="mean", median="median", buys="count",
                                 beat=lambda s: (s > 0).mean())
    return out.reindex([o for o in order if o in out.index])


# ---------- charts ----------

def theme_colors() -> dict:
    try:
        kind = st.context.theme.type or "light"
    except Exception:
        kind = "light"
    return PALETTE["dark" if kind == "dark" else "light"]


def style(fig: go.Figure, c: dict, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=4, r=4, t=36, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=c["ink2"]),
        hoverlabel=dict(font=dict(family=FONT, size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None, font=dict(color=c["ink2"])),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=c["baseline"], automargin=True,
                     tickfont=dict(color=c["muted"]))
    fig.update_yaxes(gridcolor=c["grid"], gridwidth=1, zeroline=False, automargin=True,
                     tickfont=dict(color=c["muted"]))
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


def event_study_chart(paths: pd.DataFrame, f: pd.DataFrame, group: str | None, order: list[str], c: dict):
    if group:
        d = paths.merge(f[["event_id", group]], on="event_id")
        keys = [k for k in order if k in set(d[group])]
    else:
        d = paths[paths["event_id"].isin(f["event_id"])].assign(_all="All buys")
        group, keys = "_all", ["All buys"]

    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=c["baseline"], width=1))
    fig.add_annotation(x=126, y=0, xref="x", yref="y", text="SPY", showarrow=False,
                       xanchor="left", xshift=8, font=dict(size=12, color=c["muted"]))

    ends = []
    for key in keys:
        g = d[d[group] == key].groupby("day")["excess"]
        curve = g.mean() * 100
        n = int(g.count().iloc[0])
        color = c["series"][order.index(key) % len(c["series"])] if key in order else c["series"][0]
        label = f"{key} ({n:,})"
        if len(keys) == 1:  # 95% confidence band for the single-series view
            se = g.std() / np.sqrt(g.count()) * 100
            fig.add_trace(go.Scatter(x=list(curve.index) + list(curve.index[::-1]),
                                     y=list(curve + 1.96 * se) + list((curve - 1.96 * se)[::-1]),
                                     fill="toself", fillcolor=hex_to_rgba(color, 0.12), line=dict(width=0),
                                     hoverinfo="skip", showlegend=False, name="95% confidence"))
        fig.add_trace(go.Scatter(
            x=curve.index, y=curve.values, mode="lines", name=label,
            line=dict(color=color, width=2, shape="spline", smoothing=0.4),
            hovertemplate=f"{key}: %{{y:+.1f}}%<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=[curve.index[-1]], y=[curve.values[-1]], mode="markers", showlegend=False, hoverinfo="skip",
            marker=dict(size=9, color=color, line=dict(color=c["surface"], width=2))))
        ends.append((curve.values[-1], key if len(keys) > 1 else ""))

    # Direct end labels when they don't collide; otherwise the legend carries identity.
    ys = sorted(v for v, _ in ends)
    span = (max(ys) - min(ys + [0])) or 1
    labeled = len(ends) <= 4 and all(b - a > 0.07 * span for a, b in zip(ys, ys[1:]))
    if labeled:
        for v, name in ends:
            fig.add_annotation(x=126, y=v, text=f"<b>{v:+.1f}%</b> {name}".strip(), showarrow=False,
                               xanchor="left", xshift=8, font=dict(size=13, color=c["ink"]))
    right = 70 if len(keys) == 1 else (190 if labeled else 44)

    style(fig, c, 420)
    fig.update_layout(showlegend=len(keys) > 1, hovermode="x unified", margin=dict(r=right))
    fig.update_xaxes(tickvals=[0, 21, 63, 126], ticktext=["0", "1 mo", "3 mo", "6 mo"],
                     title=dict(text="Time since the filing", font=dict(size=12, color=c["muted"])),
                     range=[0, 126], showspikes=True, spikecolor=c["baseline"], spikethickness=1)
    fig.update_yaxes(ticksuffix="%", title=None)
    return fig


def horizon_table(f: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, col in HORIZONS.items():
        s = f[col].dropna()
        rows.append((name, s.mean() * 100, s.median() * 100, len(s), (s > 0).mean() * 100))
    return pd.DataFrame(rows, columns=["horizon", "avg", "median", "n", "beat"])


def horizon_chart(h: pd.DataFrame, c: dict):
    fig = go.Figure()
    for i, (col, label) in enumerate([("avg", "Average"), ("median", "Median")]):
        fig.add_trace(go.Bar(
            x=h["horizon"], y=h[col], name=label, marker=dict(color=c["series"][i], cornerradius=4),
            text=[f"{v:+.1f}%" for v in h[col]], textposition="outside", cliponaxis=False,
            textfont=dict(color=c["ink2"], size=12),
            customdata=h[["n", "beat"]],
            hovertemplate=f"{label}: %{{y:+.1f}}%<br>%{{customdata[0]:,}} buys, %{{customdata[1]:.0f}}% beat SPY<extra></extra>"))
    style(fig, c, 320)
    fig.update_layout(showlegend=True, barmode="group", bargap=0.5, bargroupgap=0.12)
    fig.update_yaxes(ticksuffix="%")
    return fig


def breakdown_chart(table: pd.DataFrame, c: dict, x_range: list[float]):
    labels = list(table.index)[::-1]  # top-to-bottom reading order
    vals = (table["avg"] * 100).values[::-1]
    fig = go.Figure(go.Bar(
        x=vals, y=labels, orientation="h", marker=dict(color=c["series"][0], cornerradius=4),
        text=[f"{v:+.1f}%" for v in vals], textposition="outside", cliponaxis=False,
        textfont=dict(color=c["ink2"], size=12),
        customdata=np.stack([table["buys"].values[::-1], table["beat"].values[::-1] * 100,
                             table["median"].values[::-1] * 100], axis=1),
        hovertemplate="%{y}: %{x:+.1f}% avg, %{customdata[2]:+.1f}% median"
                      "<br>%{customdata[0]:,.0f} buys, %{customdata[1]:.0f}% beat SPY<extra></extra>"))
    style(fig, c, 60 + 44 * len(labels))
    fig.update_layout(bargap=0.45, margin=dict(l=4, r=56, t=8, b=4))
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=c["grid"], zeroline=True,
                     zerolinecolor=c["baseline"], zerolinewidth=1, range=x_range)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=c["ink2"]), ticklabelstandoff=8)
    return fig


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ---------- page ----------

if not DB_PATH.exists():
    st.title("Insider Trading Signal Tracker")
    st.error("No dashboard data yet. Run `python src/load_sec.py`, `python src/load_prices.py` "
             "and `python src/analyze.py` first.")
    st.stop()

signals, paths, latest, meta = load_data()
c = theme_colors()

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    dmin, dmax = signals["filing_date"].min().date(), signals["filing_date"].max().date()
    date_range = st.slider("Filing date", min_value=dmin, max_value=dmax, value=(dmin, dmax), format="MMM YYYY")
    roles = st.multiselect("Insider role", [r for r in ROLE_ORDER if r in set(signals["role"])],
                           default=[r for r in ROLE_ORDER if r in set(signals["role"])])
    min_size = st.select_slider("Minimum purchase", options=[10_000, 50_000, 100_000, 250_000, 1_000_000],
                                value=10_000, format_func=lambda v: f"${v / 1000:,.0f}K" if v < 1e6 else "$1M")
    no_plans = st.toggle("Exclude 10b5-1 plan buys", help="Pre-scheduled purchases carry less information.")
    clusters_only = st.toggle("Cluster buys only", help="3+ different insiders bought within 30 days.")
    st.caption(f"Data through {pd.Timestamp(meta['last_filing']):%b %d, %Y} · rebuilt {meta['built_at'][:10]}")


def apply_filters(df: pd.DataFrame, use_dates: bool = True) -> pd.DataFrame:
    m = df["role"].isin(roles) & (df["dollar_value"] >= min_size)
    if use_dates:
        m &= df["filing_date"].dt.date.between(*date_range)
    if no_plans:
        m &= df["plan"] != "10b5-1 plan"
    if clusters_only and "buy_type" in df:
        m &= df["buy_type"] == "Cluster (3+ insiders)"
    return df[m]


f = apply_filters(signals)

st.title("Insider Trading Signal Tracker")
st.markdown(
    f"When CEOs, CFOs and directors buy their own company's stock on the open market, does the stock beat the market? "
    f"**{len(signals):,}** insider purchases from SEC Form 4 filings, "
    f"{pd.Timestamp(meta['first_filing']):%b %Y} to {pd.Timestamp(meta['last_filing']):%b %Y}.")

if f["excess_3m"].notna().sum() == 0:
    st.warning("No purchases match these filters. Widen them in the sidebar.")
    st.stop()

s3 = f["excess_3m"].dropna()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Insider buys analyzed", f"{len(f):,}")
k2.metric("Avg 3-month return vs SPY", pct(s3.mean()))
k3.metric("Median 3-month return vs SPY", pct(s3.median()))
k4.metric("Beat SPY after 3 months", pct((s3 > 0).mean(), signed=False))

tab_signal, tab_drivers, tab_insiders, tab_latest, tab_method = st.tabs(
    ["The signal", "What drives it", "Top insiders", "Latest buys", "Methodology"])

with tab_signal:
    full = f[f["event_id"].isin(paths["event_id"])]
    if full.empty:
        st.info("None of the filtered buys has 6 months of price history yet.")
    else:
        e6 = full["excess_6m"]
        st.subheader(f"Six months after the filing, the average insider buy was {pct(e6.mean())} vs SPY")
        st.caption(f"Median {pct(e6.median())} · {(e6 > 0).mean() * 100:.0f}% beat SPY · "
                   f"{len(full):,} buys with a full 6 months of prices. Shaded band = 95% confidence interval.")
        compare = st.segmented_control("Compare by", ["All buys", "Role", "Cluster vs solo", "Purchase size"],
                                       default="All buys")
        group, order = {
            "Role": ("role", ROLE_ORDER),
            "Cluster vs solo": ("buy_type", ["Cluster (3+ insiders)", "Solo or pair"]),
            "Purchase size": ("size_bucket", SIZE_ORDER),
        }.get(compare or "All buys", (None, []))
        show(event_study_chart(paths, full, group, order, c))

    st.subheader("Average vs median at each horizon")
    st.caption("A gap between the two means a few big winners are pulling the average up.")
    h = horizon_table(f)
    chart_col, table_col = st.columns([3, 2], gap="large")
    with chart_col:
        show(horizon_chart(h, c))
    with table_col:
        st.dataframe(h, hide_index=True, width="stretch", column_config={
            "horizon": "Horizon",
            "avg": st.column_config.NumberColumn("Average", format="%+.1f%%"),
            "median": st.column_config.NumberColumn("Median", format="%+.1f%%"),
            "n": st.column_config.NumberColumn("Buys", format="localized"),
            "beat": st.column_config.NumberColumn("Beat SPY", format="%.0f%%"),
        })

with tab_drivers:
    horizon = st.segmented_control("Horizon", list(HORIZONS), default="3 months", key="drivers_horizon")
    col = HORIZONS[horizon or "3 months"]
    st.caption(f"Average return vs SPY over {horizon or '3 months'}. All four charts share one scale. "
               "Hover a bar for the median, count and win rate.")
    tables = {
        "By insider role": summarize(f, "role", col, ROLE_ORDER),
        "By purchase size": summarize(f, "size_bucket", col, SIZE_ORDER),
        "Cluster vs solo buys": summarize(f, "buy_type", col, ["Cluster (3+ insiders)", "Solo or pair"]),
        "10b5-1 plan vs discretionary": summarize(f, "plan", col, ["Discretionary", "10b5-1 plan", "Not reported"]),
    }
    all_avgs = pd.concat([t["avg"] for t in tables.values()]) * 100
    pad = (all_avgs.max() - min(all_avgs.min(), 0)) * 0.08 or 1
    x_range = [min(all_avgs.min(), 0) - (pad if all_avgs.min() < 0 else 0), max(all_avgs.max(), 0) + pad]
    left, right = st.columns(2, gap="large")
    for i, (title, table) in enumerate(tables.items()):
        with (left if i % 2 == 0 else right):
            st.markdown(f"**{title}**")
            if table.empty:
                st.caption("No data for these filters.")
            else:
                show(breakdown_chart(table, c, x_range))

    with st.expander("See the numbers"):
        combined = pd.concat({k: v for k, v in tables.items() if not v.empty}, names=["Breakdown", "Group"])
        combined = combined.reset_index()
        for k in ("avg", "median", "beat"):
            combined[k] = combined[k] * 100
        st.dataframe(combined, hide_index=True, width="stretch", column_config={
            "avg": st.column_config.NumberColumn("Average vs SPY", format="%+.1f%%"),
            "median": st.column_config.NumberColumn("Median vs SPY", format="%+.1f%%"),
            "buys": st.column_config.NumberColumn("Buys", format="%d"),
            "beat": st.column_config.NumberColumn("Beat SPY", format="%.0f%%"),
        })

with tab_insiders:
    min_buys = st.slider("Minimum number of buys", 2, 10, 3)
    d = f.dropna(subset=["excess_3m"])
    board = (d.groupby("owner_cik")
              .agg(insider=("owner_name", "last"),
                   tickers=("ticker", lambda s: ", ".join(sorted(set(s)))),
                   buys=("excess_3m", "count"),
                   avg=("excess_3m", "mean"),
                   beat=("excess_3m", lambda s: (s > 0).mean()),
                   total=("dollar_value", "sum"))
              .query("buys >= @min_buys")
              .sort_values("avg", ascending=False)
              .head(25)
              .reset_index(drop=True))
    board.insert(0, "rank", range(1, len(board) + 1))
    board["avg"] *= 100
    board["beat"] *= 100
    st.subheader("Insiders with the best track records")
    st.caption("Ranked by average 3-month return vs SPY. This looks backward: a strong record here "
               "doesn't prove the next buy will win.")
    st.dataframe(board, hide_index=True, width="stretch", column_config={
        "rank": st.column_config.NumberColumn("#", width="small"),
        "insider": "Insider",
        "tickers": "Stocks bought",
        "buys": st.column_config.NumberColumn("Buys"),
        "avg": st.column_config.NumberColumn("Avg vs SPY (3 mo)", format="%+.1f%%"),
        "beat": st.column_config.NumberColumn("Beat SPY", format="%.0f%%"),
        "total": st.column_config.NumberColumn("Total bought ($)", format="compact"),
    })

with tab_latest:
    feed = apply_filters(latest, use_dates=False).sort_values(["filing_date", "dollar_value"], ascending=False)
    feed = feed.assign(
        link=[sec_link(cik, acc) for cik, acc in zip(feed["issuer_cik"], feed["accession_number"])],
        excess_1m=feed["excess_1m"] * 100)
    st.subheader("Latest insider buys")
    st.caption(f"{len(feed):,} purchases filed in the last 6 months that match your filters. "
               "Returns appear once a month of prices is available.")
    st.dataframe(
        feed[["filing_date", "ticker", "issuer_name", "owner_name", "role", "dollar_value", "excess_1m", "link"]],
        hide_index=True, width="stretch", height=560, column_config={
            "filing_date": st.column_config.DateColumn("Filed", format="MMM D, YYYY"),
            "ticker": "Ticker",
            "issuer_name": "Company",
            "owner_name": "Insider",
            "role": "Role",
            "dollar_value": st.column_config.NumberColumn("Amount ($)", format="compact"),
            "excess_1m": st.column_config.NumberColumn("vs SPY (1 mo)", format="%+.1f%%"),
            "link": st.column_config.LinkColumn("Filing", display_text="SEC filing"),
        })

with tab_method:
    st.markdown("""
**Data.** Every original Form 4 filed with the SEC (from the SEC's quarterly Insider Transactions Data Sets),
matched to adjusted daily closing prices. SPY stands in for the market.

**What counts as a buy.** Open-market purchases only (transaction code P) of at least $10,000 at $1+ per share.
Amended filings (4/A) are skipped so trades aren't counted twice, and joint filings count once.

**When the clock starts.** At the close of the first trading day *after the filing date*, not the trade date.
Investors can't see a trade until it's filed, so starting earlier would be look-ahead bias.

**How returns are measured.** The stock's return minus SPY's return over the same 21, 63 and 126 trading days
(about 1, 3 and 6 months). The event-study curve averages buys that have a full 6 months of prices.

**Limitations**
- *Survivorship bias:* stocks that were delisted often have no price data, so failures drop out and results look better than reality.
- *No trading costs:* small stocks can have wide bid-ask spreads.
- *Overlapping buys:* several insiders buying the same stock in the same weeks aren't independent bets.
- *Backward-looking rankings:* the top-insiders list describes the past, not a forecast.
""")
    st.caption("Built with Python, SQLite (window functions, CTEs, recursive queries), pandas, Plotly and Streamlit. "
               "Not investment advice.")
