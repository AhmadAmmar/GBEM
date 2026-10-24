"""How stable are predictions for the same buildings from year to year? The noise floor for monitoring change.

    python temporal_stability.py --area belfast|london [--name stab2000]

Input: predictions of models/predict_footprints.py for a random sample of dwelling footprints in every year 2020-2025
(run first: python models/predict_footprints.py --area <area> --sample-buildings 2000 --name stab2000). The model is
fixed, so a difference between years comes only from the yearly satellite composites. Most buildings do not change
in six years, so the spread of their predictions is the noise of a monitoring system built on these data.
Reported per area: buildings, years, the median and 90th percentile of the per-building standard deviation of predicted
SAP across years, the mean absolute change between consecutive years, the share of buildings whose predicted band
changes at least once, and the minimum detectable change between two years at 95% confidence
(1.96 x sqrt(2) x median standard deviation).
Output: data/<area>/model/deploy/temporal_stability_<name>.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--name", default="stab2000")
    a = ap.parse_args()
    out = DATA / a.area / "model/deploy"
    p = pd.read_csv(out / f"predictions_{a.name}.csv")
    w = p.pivot_table(index="fp_id", columns="year", values="pred_sap")
    w = w.dropna()
    sd = w.std(axis=1, ddof=1)
    step = w.diff(axis=1).abs().stack().mean()
    bands = p.pivot_table(index="fp_id", columns="year", values="pred_band", aggfunc="first").loc[w.index]
    changed = (bands.nunique(axis=1) > 1).mean()
    yearly = w.mean()
    res = pd.DataFrame([{"area": a.area, "buildings": len(w), "years": f"{w.columns.min()}-{w.columns.max()}",
                         "sd_median": sd.median(), "sd_p90": sd.quantile(0.9), "mean_abs_year_change": step,
                         "share_band_changes": changed, "min_detectable_change_95": 1.96 * np.sqrt(2) * sd.median(),
                         "yearly_mean_range": yearly.max() - yearly.min(),
                         "outside_aoa_share": p["outside_aoa"].astype(str).eq("True").mean()}]).round(3)
    res.to_csv(keep(out / f"temporal_stability_{a.name}.csv"), index=False)
    print(res.T.to_string()); print("mean predicted SAP by year:", yearly.round(2).to_dict())


if __name__ == "__main__":
    main()
