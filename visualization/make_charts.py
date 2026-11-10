"""
make_charts.py - Part 4: static figures (PNG) from the analysis outputs in output/*.csv.

    python visualization/make_charts.py      -> report/figures/fig*.png

Style: one hue per job (blue = magnitude/series 1, orange = comparison series 2),
thin marks, recessive grid, direct labels only where they carry the finding,
never a dual y-axis.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

OUT, FIG = config.OUTPUT_DIR, config.FIG_DIR
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#8a8984"
INK, INK2 = "#0b0b0b", "#52514e"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
ORDINAL = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#d6d5d0",
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": "#ebeae6", "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left",
})


def read(name):
    return pd.read_csv(os.path.join(OUT, f"{name}.csv"))


def save(fig, name):
    path = os.path.join(FIG, name)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("  wrote", path)


def money(x, _=None):
    return f"${x / 1e6:.1f}M" if abs(x) >= 1e6 else f"${x / 1e3:.0f}k"


# ---------------------------------------------------------------- 1. sales over time
def fig_daily_revenue():
    d = read("sql_q3_daily_revenue_rolling")
    d["txn_date"] = pd.to_datetime(d["txn_date"])
    d = d.iloc[1:-1]  # drop the two partial edge days
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(d.txn_date, d.revenue, color=BLUE, lw=1, alpha=0.45, label="Daily revenue")
    ax.plot(d.txn_date, d.revenue_7d_avg, color=BLUE, lw=2.2, label="7-day rolling average")
    ax.yaxis.set_major_formatter(money)
    ax.set_ylim(0, d.revenue.max() * 1.15)
    ax.set_title(f"Daily revenue is flat at ~\\${d.revenue.mean() / 1e3:,.0f}k/day "      # \\$ = literal $ in matplotlib
                 f"(s.d. \\${d.revenue.std() / 1e3:,.0f}k) across the window")
    ax.legend(frameon=False, loc="lower right")
    ax.set_ylabel("Net revenue")
    save(fig, "fig1_daily_revenue.png")


# ---------------------------------------------------------------- 2. revenue by category
def fig_category_revenue():
    d = read("mongo_revenue_category_month").groupby("category", as_index=False)[["revenue", "est_profit"]].sum()
    d = d.sort_values("revenue")
    fig, axes = plt.subplots(1, 2, figsize=(10, 6.2), sharey=True, gridspec_kw={"wspace": 0.08})
    for ax, col, color, title in [(axes[0], "revenue", BLUE, "Revenue"),
                                  (axes[1], "est_profit", ORANGE, "Estimated gross profit")]:
        ax.barh(d.category, d[col], color=color, height=0.72, edgecolor="#fcfcfb", linewidth=1)
        ax.xaxis.set_major_formatter(money)
        ax.set_title(title, fontsize=11)
        ax.grid(axis="y", visible=False)
    margin = d.est_profit / d.revenue
    top, low = d.loc[margin.idxmax()], d.loc[margin.idxmin()]
    fig.suptitle("Revenue is even across categories; profit is not (margins drive the spread)",
                 x=0.02, ha="left", fontweight="bold", fontsize=12)
    axes[1].annotate(f"{top.est_profit / top.revenue:.0%} margin", (top.est_profit, top.category),
                     xytext=(4, 0), textcoords="offset points", va="center", fontsize=8, color=INK2)
    axes[1].annotate(f"{low.est_profit / low.revenue:.0%} margin", (low.est_profit, low.category),
                     xytext=(4, 0), textcoords="offset points", va="center", fontsize=8, color=INK2)
    save(fig, "fig2_category_revenue_profit.png")


# ---------------------------------------------------------------- 3. funnel
def fig_funnel():
    d = read("funnel_overall")
    fig, ax = plt.subplots(figsize=(9, 3.6))
    y = np.arange(len(d))[::-1]
    ax.barh(y, d.sessions, color=ORDINAL, height=0.7)
    for yi, (_, r) in zip(y, d.iterrows()):
        txt = f"{r.sessions:,.0f}  ({r.pct_of_sessions:.1f}%)"
        if r.stage[0] != "1":
            txt += f"   step: {r.step_conversion_pct:.0f}%"
        ax.text(r.sessions + d.sessions.max() * 0.01, yi, txt, va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [s[3:] for s in d.stage])
    ax.set_xlim(0, d.sessions.max() * 1.45)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Sessions")
    lost = 100 - d.step_conversion_pct
    ax.set_title(f"Biggest leaks: cart -> checkout ({lost.iloc[3]:.0f}% lost) and "
                 f"checkout -> purchase ({lost.iloc[4]:.0f}% lost)")
    save(fig, "fig3_conversion_funnel.png")


# ---------------------------------------------------------------- 4. CLV segments
def fig_clv_segments():
    d = read("clv_segments")
    d = d[d.segment != "No purchase"].sort_values("avg_clv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, gridspec_kw={"wspace": 0.08})
    axes[0].barh(d.segment, d.users, color=GRAY, height=0.7)
    axes[0].set_title("Customers", fontsize=11)
    axes[1].barh(d.segment, d.avg_clv, color=BLUE, height=0.7)
    axes[1].set_title("Average estimated CLV", fontsize=11)
    axes[1].xaxis.set_major_formatter(lambda x, _: f"${x:,.0f}")
    for ax, col, fmt in [(axes[0], "users", "{:,.0f}"), (axes[1], "share_of_clv_pct", "{:.0f}% of total CLV")]:
        ax.grid(axis="y", visible=False)
    for seg, v, s in zip(d.segment, d.avg_clv, d.share_of_clv_pct):
        axes[1].text(v + 40, seg, f"{s:.0f}% of CLV", va="center", fontsize=8, color=INK2)
    axes[1].set_xlim(0, d.avg_clv.max() * 1.35)
    total = read("clv_segments").users.sum()
    ch = d[d.segment == "Champions"].iloc[0]
    risk = d[d.segment == "At risk - high value"].iloc[0]
    fig.suptitle(f"{100 * ch.users / total:.0f}% of customers ('Champions') hold {ch.share_of_clv_pct:.0f}% of "
                 f"lifetime value; {risk.users:,.0f} high-value customers are lapsing",
                 x=0.02, y=1.03, ha="left", fontweight="bold", fontsize=11.5)
    save(fig, "fig4_clv_segments.png")


# ---------------------------------------------------------------- 5. cohort heatmap
def fig_cohort():
    d = read("cohort_retention_pivot").set_index("registration_month")
    sizes = d.pop("cohort_users")
    d = d.drop(columns=[c for c in d.columns if c.endswith("-11")], errors="ignore")  # 1-day partial month
    fig, ax = plt.subplots(figsize=(7, 3.8))
    cmap = LinearSegmentedColormap.from_list("seq", SEQ)
    im = ax.imshow(d.values, cmap=cmap, vmin=70, vmax=90, aspect="auto")
    ax.set_xticks(range(len(d.columns)), d.columns)
    ax.set_yticks(range(len(d.index)), [f"{i}  (n={sizes[i]:,})" for i in d.index])
    for i in range(d.shape[0]):
        for j in range(d.shape[1]):
            v = d.values[i, j]
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=9,
                    color="white" if v > 82 else INK)
    ax.grid(False)
    ax.set_xlabel("Purchase month")
    ax.set_ylabel("Registration cohort")
    cb = fig.colorbar(im, ax=ax, fraction=0.04)
    cb.set_label("% of cohort buying", color=INK2)
    cb.outline.set_visible(False)
    full = d.iloc[:, 1:] if d.shape[1] > 2 else d     # first month of the window is partial
    ax.set_title(f"Cohort activity barely decays: ~{full.values.mean():.0f}% of every cohort buys in each full month",
                 fontsize=11)
    save(fig, "fig5_cohort_retention.png")


# ---------------------------------------------------------------- 6. viewed vs sold
def fig_viewed_vs_sold():
    d = read("sql_q5_viewed_vs_sold")
    d = d[d.is_active]                       # inactive products are never shown or sold
    d["sold_out"] = d.current_stock < 3      # stock exhausted during the window
    ins, out = d[~d.sold_out], d[d.sold_out]
    r_in = np.corrcoef(ins.views, ins.units_sold)[0, 1]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.scatter(ins.views, ins.units_sold, s=9, color=BLUE, alpha=0.35, linewidths=0,
               label=f"In stock ({len(ins):,} products)")
    ax.scatter(out.views, out.units_sold, s=12, color=ORANGE, alpha=0.8, linewidths=0,
               label=f"Sold out by end of window ({len(out):,})")
    ax.set_xlabel("Product-page views (sessions)")
    ax.set_ylabel("Units sold (all channels)")
    ax.legend(frameon=False, loc="upper left")
    ax.set_title(f"Stock-outs, not demand, create the view-sales link (in-stock r = {r_in:.2f})", fontsize=11)
    save(fig, "fig6_viewed_vs_sold.png")


# ---------------------------------------------------------------- 7. engagement vs value
def fig_engagement():
    d = read("sql_qB1_engagement_vs_value_mongo_x_hbase")
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    labels = [s[3:] for s in d.engagement_band]
    ax.bar(labels, d.avg_spent, color=BLUE, width=0.6)
    for x, v, u in zip(labels, d.avg_spent, d.users):
        ax.text(x, v + 80, f"${v:,.0f}\n{u:,} users", ha="center", fontsize=8.5, color=INK2)
    ax.set_ylim(0, d.avg_spent.max() * 1.25)
    ax.yaxis.set_major_formatter(lambda x, _: f"${x:,.0f}")
    ax.grid(axis="x", visible=False)
    ax.set_xlabel("Sessions in 90 days (HBase user_sessions)")
    ax.set_ylabel("Avg spend (MongoDB users)")
    up = 100 * (d.avg_spent.iloc[-1] / d.avg_spent.iloc[0] - 1)
    ax.set_title(f"More sessions -> more spend: 25+ session users spend {up:.0f}% more than <15")
    save(fig, "fig7_engagement_vs_spend.png")


if __name__ == "__main__":
    for f in [fig_daily_revenue, fig_category_revenue, fig_funnel, fig_clv_segments, fig_cohort,
              fig_viewed_vs_sold, fig_engagement]:
        f()
