#!/bin/bash
# Model comparison on identical spatial folds, one array task per city and model.
#   sbatch --array=0-11 ~/phd/code/hpc/model_compare.sbatch
#SBATCH --job-name=model_compare
#SBATCH --partition=k2-medpri
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --output=/users/aammar/phd/logs/model_compare_%A_%a.out

unset PYTHONPATH PYTHONHOME
PY=~/phd/envs/eo/bin/python
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK MKL_NUM_THREADS=$SLURM_CPUS_PER_TASK

AREAS=(belfast belfast belfast belfast belfast london london london london london belfast london)
MODELS=(rf lgbm xgb mlp graph rf lgbm xgb mlp graph graph graph)
YEARS=("2024" "2024" "2024" "2024" "2024" "2024" "2024" "2024" "2024" "2024" "2021 2022 2023 2024" "2021 2022 2023 2024")
NAMES=(rf lgbm xgb mlp graph rf lgbm xgb mlp graph spatiotemporal spatiotemporal)

i=$SLURM_ARRAY_TASK_ID
echo "task $i: ${AREAS[$i]} ${MODELS[$i]} years ${YEARS[$i]} on $(hostname)"
cd ~/phd/code
$PY models/model_compare.py --area "${AREAS[$i]}" --years ${YEARS[$i]} --models "${MODELS[$i]}" \
    --featureset eo_morph --sample 50000 --trials 25 --tune-rows 15000 --tag "${NAMES[$i]}_eo_morph"
