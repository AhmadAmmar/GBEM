import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from datetime import datetime

# Define the project timeline tasks
tasks = [
    ("Literature Review", "2024-09-16", "2027-09-16", "continuous"),
    ("Systematic Review Paper (Scoping & Scientometric Analyses)", "2024-12-15", "2025-09-01", "in_progress"),
    ("Data Acquisition, Cleaning, Preprocessing", "2024-11-01", "2026-02-01", "in_progress"),
    ("Exploratory Analysis & Feature Engineering", "2024-11-15", "2026-02-01", "in_progress"),
    ("Baseline ML Model Development", "2024-12-01", "2025-08-01", "in_progress"),
    ("Clustering, Analytics, Refinements & Further Data Integration", "2025-03-01", "2026-08-01", "planned"),
    ("Conference & Journal Identification", "2024-09-16", "2027-09-16", "continuous"),
    ("Advanced ML/DL & Ensemble Modeling", "2025-08-01", "2026-03-01", "planned"),
    ("First Publication Based on Development of Data & Methods", "2025-10-01", "2026-05-01", "planned"),
    ("Study Area Expansion & Largescale Mapping", "2026-03-01", "2026-08-01", "planned"),
    ("Validations & Policy Integration", "2026-03-01", "2026-08-01", "planned"),
    ("BIM/BEM Integration Possibilities", "2026-05-01", "2026-10-01", "planned"),
    ("Visualization & Dashboard Development", "2026-09-01", "2027-02-01", "planned"),
    ("Research Paper Writing & Conference Submission", "2026-09-01", "2027-02-01", "planned"),
    ("Final Model Tweaks & Open-Sourcing", "2026-09-01", "2027-02-01", "planned"),
    ("Additional Case Studies & Impact Analysis", "2027-03-01", "2027-08-01", "planned"),
    ("Final Thesis Writing & Submission", "2027-03-01", "2027-09-16", "planned"),
    ("Peer-Reviewed Publications & Conference Presentations", "2027-03-01", "2027-09-16", "planned"),
    ("Industrial Linkages & Field Engagements", "2027-03-01", "2027-12-31", "planned")
]

# Convert data into a DataFrame
df = pd.DataFrame(tasks, columns=["Task", "Start", "End", "Category"])

# Convert dates
df["Start"] = pd.to_datetime(df["Start"])
df["End"] = pd.to_datetime(df["End"])

# Define colors for categories
colors = {"continuous": "gold", "in_progress": "royalblue", "planned": "seagreen"}

# Plot settings
fig, ax = plt.subplots(figsize=(12, 6))

# Plot Gantt bars
for i, row in df.iterrows():
    ax.barh(
        row["Task"], 
        row["End"] - row["Start"], 
        left=row["Start"], 
        color=colors[row["Category"]], 
        label=row["Category"] if row["Category"] not in df["Category"][:i].values else ""
    )

# Formatting x-axis with Sep and Feb labels explicitly
start_date = datetime(2024, 9, 1)
end_date = datetime(2027, 9, 30)
xticks = pd.date_range(start=start_date, end=end_date, freq="6M")  # Every 6 months
xticklabels = [d.strftime('%b %Y') for d in xticks]

ax.set_xticks(xticks)
ax.set_xticklabels(xticklabels, rotation=45)

# Milestones
milestones = [
    ("Start", "2024-09-16"),
    ("Today", "2025-02-10"),
    ("End", "2027-09-16")
]
for label, date in milestones:
    date_dt = datetime.strptime(date, "%Y-%m-%d")
    ax.axvline(date_dt, color='red', linestyle='dashed', linewidth=1)
    ax.text(date_dt, df.shape[0] + 0.5, label, rotation=90, verticalalignment='bottom', fontsize=10, fontweight='bold', color='red')

# Labels and adjusted legend position
ax.set_xlabel("Timeline (Months)")
ax.set_title("PhD Project Timeline - Gantt Chart")
ax.legend(title="Task Type", loc="upper left", bbox_to_anchor=(0.02, 0.95))  # Move legend further up and left

# Save and show the plot
plt.tight_layout()
plt.savefig("phd_gantt_chart_final.png", dpi=300)
plt.show()