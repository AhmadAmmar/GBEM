"""
rf_epc_tree_walk_right_clean.py

Right-only animation: decision-path text + Random Forest vote bar chart
for a synthetic EPC example, using EO/RS-style features.

Exports:
  - rf_epc_tree_walk_right_clean.mp4   (if ffmpeg is available)
  - rf_epc_tree_walk_right_clean.gif   (fallback)

Run:
  python rf_epc_tree_walk_right_clean.py
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter, PillowWriter

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

# ------------------------ 1. Synthetic data ------------------------

np.random.seed(42)
N = 1200

age = np.random.randint(1, 6, size=N)
height = np.random.uniform(4, 25, size=N)
ndvi = np.random.uniform(0.0, 0.8, size=N)
ndbi = np.random.uniform(-0.2, 0.5, size=N)
sar_ratio = np.random.uniform(-15, 5, size=N)
lst = np.random.normal(loc=20, scale=3, size=N)
lst = lst + 4 * ndbi - 3 * ndvi  # hotter & built-up = worse

feature_names = ["Age_band", "Height", "NDVI", "NDBI", "LST", "SAR_ratio"]
X_raw = np.vstack([age, height, ndvi, ndbi, lst, sar_ratio]).T

scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(X_raw)

score = (
    0.35 * X_scaled[:, 0]
    - 0.15 * X_scaled[:, 1]
    - 0.35 * X_scaled[:, 2]
    + 0.30 * X_scaled[:, 3]
    + 0.40 * X_scaled[:, 4]
    + 0.10 * X_scaled[:, 5]
    + np.random.normal(0, 0.08, size=N)
)

epc_bins = np.quantile(score, [0.15, 0.30, 0.45, 0.60, 0.75, 0.90])
epc_index = np.digitize(score, epc_bins)
epc_labels = np.array(list("ABCDEFG"))
y = pd.Series(epc_labels[epc_index], name="EPC")

df = pd.DataFrame(
    {
        "Age_band": age,
        "Height": height,
        "NDVI": ndvi,
        "NDBI": ndbi,
        "LST": lst,
        "SAR_ratio": sar_ratio,
        "EPC": y,
    }
)

X = df[feature_names].copy()

# ------------------------ 2. Random Forest ------------------------

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, stratify=y, random_state=0
)

rf = RandomForestClassifier(
    n_estimators=3,      # tiny forest for visual clarity
    max_depth=3,
    min_samples_leaf=5,
    random_state=0,
)
rf.fit(X_train, y_train)

classes = rf.classes_
n_classes = len(classes)

# Choose one example building
example_idx = X_test.sample(1, random_state=1).index[0]
x_example = X_test.loc[example_idx].values.reshape(1, -1)
y_true = y_test.loc[example_idx]

print("Animating path for example building:")
print(df.loc[example_idx])
print()

# ------------------------ 3. Tree paths & votes ------------------------

tree_paths = []
tree_preds_idx = []

for t_idx, tree in enumerate(rf.estimators_):
    tree_ = tree.tree_
    node_indicator = tree.decision_path(x_example)
    node_index = node_indicator.indices

    proba_t = tree.predict_proba(x_example)[0]
    pred_idx = np.argmax(proba_t)
    tree_preds_idx.append(pred_idx)

    lines = []
    for depth, node_id in enumerate(node_index[:-1]):  # exclude leaf
        feat_id = tree_.feature[node_id]
        thresh = tree_.threshold[node_id]
        feat_name = feature_names[feat_id]
        x_val = x_example[0, feat_id]

        go_left = x_val <= thresh
        direction = "go LEFT" if go_left else "go RIGHT"
        comparator = "<=" if go_left else ">"

        line = (
            f"Node {depth}:  {feat_name} {comparator} {thresh:.2f}?  "
            f"value = {x_val:.2f}  →  {direction}"
        )
        lines.append(line)

    leaf_line = (
        f"Leaf prediction: EPC {classes[pred_idx]} "
        f"(tree {t_idx+1} vote, p={proba_t[pred_idx]:.2f})"
    )
    tree_paths.append({"splits": lines, "leaf_line": leaf_line})

forest_proba = rf.predict_proba(x_example)[0]
forest_pred_idx = np.argmax(forest_proba)

# ------------------------ 4. Animation steps ------------------------

steps = []
for t_idx, path in enumerate(tree_paths):
    n_splits = len(path["splits"])
    for s_idx in range(n_splits):
        steps.append({"kind": "split", "tree_idx": t_idx, "split_idx": s_idx})
    steps.append({"kind": "leaf", "tree_idx": t_idx})
steps.append({"kind": "forest_summary"})
n_frames = len(steps)

# ------------------------ 5. Figure layout (right-only) ------------------------

plt.style.use("default")
fig = plt.figure(figsize=(8, 7))
gs = fig.add_gridspec(
    2, 1,
    height_ratios=[1.8, 1.0]  # more space for text
)

ax_text = fig.add_subplot(gs[0, 0])
ax_bar = fig.add_subplot(gs[1, 0])

fig.suptitle(
    "How a Random Forest predicts an EPC band\n"
    "using EO/RS & geospatial features",
    fontsize=13,
    weight="bold",
)

ax_text.axis("off")
text_artist = ax_text.text(
    0.0,
    1.0,
    "",
    transform=ax_text.transAxes,
    va="top",
    ha="left",
    fontsize=9,
    linespacing=1.4,
)

epc_colors = ["#1a9850", "#66bd63", "#d9ef8b",
              "#fee08b", "#fdae61", "#f46d43", "#d73027"]

bars = ax_bar.bar(
    classes,
    np.zeros(n_classes),
    color=epc_colors[:n_classes],
    alpha=0.85,
)
ax_bar.set_ylim(0, 1.0)
ax_bar.set_ylabel("Vote proportion")
ax_bar.set_title("Forest votes so far")
ax_bar.grid(axis="y", alpha=0.25)
ax_bar.set_yticks([0, 0.25, 0.5, 0.75, 1.0])

summary_text = ax_bar.text(
    0.02,
    0.98,
    "",
    transform=ax_bar.transAxes,
    va="top",
    ha="left",
    fontsize=9,
)

plt.tight_layout(rect=[0, 0, 1, 0.92])

# ------------------------ 6. Voting helper ------------------------

def votes_up_to_step(step_idx):
    vote_counts = np.zeros(n_classes, dtype=int)
    leaf_positions = []
    for t_idx in range(len(tree_paths)):
        idxs = [
            i for i, s in enumerate(steps)
            if s["kind"] == "leaf" and s["tree_idx"] == t_idx
        ]
        leaf_positions.append(idxs[0])

    for t_idx, leaf_idx in enumerate(leaf_positions):
        if step_idx >= leaf_idx:
            vote_counts[tree_preds_idx[t_idx]] += 1
    return vote_counts

# ------------------------ 7. Animation update ------------------------

def update(frame):
    step = steps[frame]

    if step["kind"] in ("split", "leaf"):
        t_idx = step["tree_idx"]
        path_info = tree_paths[t_idx]
        lines = []

        lines.append(f"Tree {t_idx + 1} of {len(tree_paths)}")
        lines.append("Decision path for this building:")
        lines.append("")

        if step["kind"] == "split":
            s_idx = step["split_idx"]
            for i in range(s_idx + 1):
                lines.append("  " + path_info["splits"][i])
        else:
            for l in path_info["splits"]:
                lines.append("  " + l)
            lines.append("")
            lines.append("  " + path_info["leaf_line"])

        lines.append("")
        lines.append("Feature values for this building:")
        for fname, val in zip(feature_names, x_example[0]):
            if fname == "Age_band":
                lines.append(f"  {fname}: {val:.0f}")
            else:
                lines.append(f"  {fname}: {val:.2f}")

        text_artist.set_fontsize(9)
        text_artist.set_text("\n".join(lines))

    elif step["kind"] == "forest_summary":
        top_probs_idx = np.argsort(forest_proba)[::-1][:3]

        lines = []
        lines.append("Forest summary (all trees done):")
        lines.append("")
        lines.append(f"  True EPC band: {y_true}")
        lines.append(
            f"  Random Forest prediction: EPC {classes[forest_pred_idx]}"
        )
        lines.append("")
        lines.append("  Top probabilities:")
        for idx in top_probs_idx:
            c = classes[idx]
            p = forest_proba[idx]
            lines.append(f"    P(EPC = {c}) = {p:.2f}")
        lines.append("")
        lines.append("Interpretation:")
        lines.append(
            "  • Each tree votes based on splits on EO/RS/geospatial"
        )
        lines.append(
            "    features (NDVI, LST, NDBI, age, height, SAR)."
        )
        lines.append(
            f"  • The forest aggregates these votes; the majority vote "
            f"is EPC {classes[forest_pred_idx]}."
        )

        text_artist.set_fontsize(8)
        text_artist.set_text("\n".join(lines))

    vote_counts = votes_up_to_step(frame)
    trees_used = max(vote_counts.sum(), 1)
    vote_props = vote_counts / trees_used

    for i, b in enumerate(bars):
        b.set_height(vote_props[i])
        b.set_alpha(0.95 if vote_counts[i] > 0 else 0.3)

    summary_lines = [
        f"True EPC: {y_true}",
        f"Trees finished so far: {trees_used}/{len(tree_paths)}",
    ]
    if trees_used == len(tree_paths):
        summary_lines.append(
            f"Final RF prediction: EPC {classes[forest_pred_idx]}"
        )
    summary_text.set_text("\n".join(summary_lines))

    return [text_artist, *bars, summary_text]

anim = FuncAnimation(
    fig,
    update,
    frames=n_frames,
    interval=1300,
    blit=False,
)

# ------------------------ 8. Save as VIDEO (MP4) + optional GIF ------------------------

SAVE = True   # keep this True to export

if SAVE:
    try:
        # MP4 video (needs ffmpeg in your environment)
        writer = FFMpegWriter(fps=1)
        anim.save("rf_epc_tree_walk_right_clean.mp4", writer=writer, dpi=150)
        print("Saved animation to rf_epc_tree_walk_right_clean.mp4")
    except Exception as e:
        print("Could not save MP4:", e)
        print("Trying GIF via PillowWriter...")
        try:
            gif_writer = PillowWriter(fps=1)
            anim.save(
                "rf_epc_tree_walk_right_clean.gif",
                writer=gif_writer,
                dpi=120,
            )
            print("Saved animation to rf_epc_tree_walk_right_clean.gif")
        except Exception as e2:
            print("Could not save GIF either:", e2)

plt.show()
