#!/bin/bash
# Runs the HEM engine on Kelvin-2 over every variant_*.json of an inputs folder as a Slurm job array.
#   sbatch --array=0-<N-1> run_hem_array.sh <inputs folder> [EPW file] [runs per task]
# Each task runs a block of variants (default 20) one after the other on one core, so many short runs make a few
# hundred tasks rather than thousands. Results go next to the inputs (variant_<id>__results/), as with run_hem.sh, so
# compare_trial.py works unchanged. Tasks skip variants that already have a results summary (safe to resubmit).
#SBATCH --job-name=hem
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --output=/users/aammar/phd/logs/%x_%A_%a.out
IN="$1"; EPW="${2:-$HOME/phd/code/epb-home-energy-model/examples/weather_data/London_weather_EnergyPlus_format.epw}"
PER="${3:-20}"
HEM=$HOME/phd/bin/hem
mapfile -t FILES < <(ls "$IN"/variant_*.json | sort)
start=$(( SLURM_ARRAY_TASK_ID * PER ))
for f in "${FILES[@]:start:PER}"; do
  b=$(basename "$f" .json)
  [ -f "$IN/${b}__results/${b}__core__results_summary.csv" ] && continue
  ( cd "$IN" && RUST_LOG=warn "$HEM" "$f" -e "$EPW" ) || echo "FAILED $f"
done
echo "task $SLURM_ARRAY_TASK_ID done: ${#FILES[@]} files in total, block of $PER from $start"
