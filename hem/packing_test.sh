#!/bin/bash
# Task-packing test on Kelvin-2: the same 1,296-run parametric study submitted with 1, 5, 20 and 100 runs per task.
#   bash packing_test.sh            (from the login node; needs the campaign inputs and run_hem_array.sh in ~/phd/jobs)
# Each setting gets its own copy of the inputs (JSON only), so no results are shared or skipped between settings.
# Afterwards, sacct with Submit/Start/End gives queue wait, wall time and core time per setting (see the echo at the end).
CAMP=$(ls -d ~/phd/scratch/data/*campaign_forms* ~/phd/scratch/data/hem_trial/*campaign_forms* 2>/dev/null | head -1)
EPW_LON=$(ls ~/phd/scratch/data/weather/*Heathrow*TMYx*.epw | head -1)
EPW_BEL=$(ls ~/phd/scratch/data/weather/*Belfast*TMYx*.epw | head -1)
OUT=~/phd/scratch/outputs/packing_$(date +%Y-%m-%d_%H%M)
mkdir -p "$OUT"; echo "inputs: $CAMP"; echo "weather: $EPW_LON | $EPW_BEL"; echo "output: $OUT"
[ -d "$CAMP" ] && [ -f "$EPW_LON" ] && [ -f "$EPW_BEL" ] || { echo "missing inputs or weather"; exit 1; }
for PER in 1 5 20 100; do
  for d in "$CAMP"/*/; do
    d=${d%/}; f=$(basename "$d"); dst=$OUT/per$PER/$f
    mkdir -p "$dst" && cp "$d"/variant_*.json "$dst"/
    n=$(ls "$dst"/variant_*.json | wc -l); last=$(( (n + PER - 1) / PER - 1 ))
    case $f in *_belfast) epw=$EPW_BEL;; *) epw=$EPW_LON;; esac
    sbatch --parsable --job-name=pack$PER --array=0-$last ~/phd/jobs/run_hem_array.sh "$dst" "$epw" "$PER"
  done
done | tee "$OUT/job_ids.txt"
echo "When all jobs have finished:"
echo "  sacct -X -P -S $(date +%Y-%m-%d) -u \$USER --name=pack1,pack5,pack20,pack100 -o JobID,JobName,Submit,Start,End,Elapsed,TotalCPU,State > ~/phd/packing_sacct.txt"
