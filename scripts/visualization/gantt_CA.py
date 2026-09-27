# phd_gantt.py
# Matplotlib-only, single figure (no subplots), no explicit colors.
# Uses hatches/alpha for categories, title outside axes, and robust milestone placement.

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.transforms as transforms
import pandas as pd
from datetime import timedelta

# ───────────────────────── Config (tweak if needed) ─────────────────────────
START_DATE = "2024-09-01"
END_DATE   = "2027-09-30"

TITLE = "PhD Project Timeline — Gantt Chart (updated 06 Oct 2025)"

# Milestone label behaviour
TOP_Y_FRAC = 0.965          # baseline vertical position (inside axes)
Y_STEP = 0.10               # vertical separation for labels that cluster by date
RIGHT_EDGE_DAYS = 30        # labels within this many days of END_DATE treated as right-edge
LEFT_EDGE_DAYS = 30         # labels within this many days of START_DATE treated as left-edge
RIGHT_EDGE_X_NUDGE_PT = 26  # nudge labels left (points) when at right edge
LEFT_EDGE_X_NUDGE_PT  = 12  # nudge labels right (points) when at left edge
CLUSTER_DAYS = 10           # dates within this many days are stacked

# Outputs
PNG_PATH = "phd_gantt_2025-10-06.png"
PDF_PATH = "phd_gantt_2025-10-06.pdf"
CSV_PATH = "phd_gantt_tasks_2025-10-06.csv"

# ───────────────────────── Data ─────────────────────────
tasks = [
    # Continuous
    ("Literature Review", "2024-09-16", "2027-09-16", "continuous"),
    ("Conference & Journal Identification", "2024-09-16", "2027-09-16", "continuous"),
    ("Code & Reproducibility (versioned env, seeds, folds)", "2024-12-01", "2027-09-16", "continuous"),

    # In progress
    ("Systematic Review + Scientometric/Scoping Paper", "2024-12-15", "2025-11-30", "in_progress"),
    ("Data acquisition, cleaning & preprocessing (London+Belfast)", "2024-11-01", "2026-02-01", "in_progress"),
    ("Feature engineering & index generation v2 (S2/S1/L8, textures)", "2025-04-11", "2026-02-01", "in_progress"),
    ("Visualization maps & dashboard (Folium/Matplotlib)", "2025-04-16", "2026-02-01", "in_progress"),
    ("Advanced ML (XGB/Ordinal) + Calibration/Uncertainty", "2025-04-02", "2026-03-01", "in_progress"),
    ("Belfast EPC + UPRN integration & analytics", "2025-08-01", "2025-11-30", "in_progress"),
    ("First methods paper (data + pipeline)", "2025-10-01", "2026-05-01", "in_progress"),

    # Completed
    ("Baseline ML models (RF multiclass/binary) + maps", "2024-12-01", "2025-08-01", "completed"),
    ("Unified GEE pipeline v1 (zonal means per building)", "2025-04-15", "2025-05-15", "completed"),

    # Planned
    ("Deep learning/Transformers (CNN/ViT) prototypes", "2025-11-01", "2026-07-01", "planned"),
    ("Study area expansion & large-scale mapping", "2026-03-01", "2026-08-01", "planned"),
    ("Validation & policy integration", "2026-03-01", "2026-08-01", "planned"),
    ("BIM/BEM integration possibilities", "2026-05-01", "2026-10-01", "planned"),
    ("Final model tweaks & open-sourcing", "2026-09-01", "2027-02-01", "planned"),
    ("Additional case studies & impact analysis", "2027-03-01", "2027-08-01", "planned"),
    ("Final thesis writing & submission", "2027-03-01", "2027-09-16", "planned"),
    ("Peer-reviewed publications & conference presentations", "2027-03-01", "2027-09-16", "planned"),
]

# Milestones — note ONLY ONE on the right edge as requested
milestones = [
    ("Project start", "2024-09-16"),
    ("HotSat-1 proposal submitted", "2025-04-11"),
    ("AGI NI lightning talk", "2025-06-07"),
    ("Belfast data produced", "2025-08-31"),
    ("Confirmation assessment presentation", "2025-10-15"),
    ("Exam/submission", "2027-09-12"),  # single right-edge milestone
]

# ───────────────────────── Plotter ─────────────────────────
def plot_gantt(tasks, milestones):
    df = pd.DataFrame(tasks, columns=["Task", "Start", "End", "Category"])
    df["Start"] = pd.to_datetime(df["Start"])
    df["End"] = pd.to_datetime(df["End"])
    df.to_csv(CSV_PATH, index=False)

    category_style = {
        "continuous":  {"hatch": "///", "alpha": 0.60},
        "in_progress": {"hatch": "...", "alpha": 0.90},
        "completed":   {"hatch": "",    "alpha": 0.40},
        "planned":     {"hatch": "xx",  "alpha": 0.80},
    }

    fig, ax = plt.subplots(figsize=(13, 8))

    # Bars (no explicit colors)
    for i, row in enumerate(df.itertuples(index=False)):
        width = row.End - row.Start
        sty = category_style.get(row.Category, {"hatch": "", "alpha": 0.9})
        ax.barh(i, width, left=row.Start, hatch=sty["hatch"], alpha=sty["alpha"])

    # Y labels
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["Task"])

    # X axis
    start_date = pd.to_datetime(START_DATE)
    end_date   = pd.to_datetime(END_DATE)
    ax.set_xlim(start_date, end_date)
    xticks = pd.date_range(start=start_date, end=end_date, freq="6MS")
    ax.set_xticks(xticks)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    # Grid
    ax.grid(axis="x", linestyle=":", alpha=0.5)

    # Title outside axes
    fig.text(0.01, 0.985, TITLE, ha="left", va="top", fontsize=16, fontweight="bold")

    # Legend
    legend_handles = [
        mpatches.Patch(hatch=sty["hatch"], alpha=sty["alpha"], label=cat.replace("_", " ").title())
        for cat, sty in category_style.items()
    ]
    ax.legend(handles=legend_handles, title="Status", loc="upper left", bbox_to_anchor=(0.01, 0.99))

    # Milestones
    ms = pd.DataFrame(milestones, columns=["label", "date"]).sort_values("date")
    ms["date"] = pd.to_datetime(ms["date"])

    # Cluster labels that are close in time (for vertical stacking)
    clusters = []
    for idx, (_, row) in enumerate(ms.iterrows()):
        if not clusters:
            clusters.append([idx]); continue
        last = clusters[-1][-1]
        if abs((ms.iloc[idx]["date"] - ms.iloc[last]["date"]).days) <= CLUSTER_DAYS:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])

    blend = transforms.blended_transform_factory(ax.transData, ax.transAxes)

    for cl in clusters:
        dates = ms.iloc[cl]["date"].tolist()
        anchor = min(dates)
        at_right = anchor > (end_date - timedelta(days=RIGHT_EDGE_DAYS))
        at_left  = anchor < (start_date + timedelta(days=LEFT_EDGE_DAYS))

        if at_right:
            x_off_pts, ha = -RIGHT_EDGE_X_NUDGE_PT, "right"
        elif at_left:
            x_off_pts, ha = LEFT_EDGE_X_NUDGE_PT, "left"
        else:
            x_off_pts, ha = 0, "center"

        for j, ridx in enumerate(cl):
            d = ms.iloc[ridx]["date"]
            label = ms.iloc[ridx]["label"]
            y = TOP_Y_FRAC - j * Y_STEP
            tform = transforms.offset_copy(blend, fig=fig, x=x_off_pts, y=0, units="points")
            ax.axvline(d, linestyle="--", linewidth=1.2)  # default style, no explicit color
            ax.text(d, y, label, rotation=90, va="top", ha=ha, fontsize=9,
                    fontweight="bold", transform=tform, zorder=5, clip_on=False)

    plt.subplots_adjust(top=0.87)
    ax.set_xlabel("Timeline")
    plt.savefig(PNG_PATH, dpi=300, bbox_inches="tight")
    plt.savefig(PDF_PATH, dpi=300, bbox_inches="tight")
    plt.show()

if __name__ == "__main__":
    plot_gantt(tasks, milestones)
