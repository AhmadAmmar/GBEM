#!/usr/bin/env bash
# Runs the HEM engine (communitiesuk/epb-home-energy-model, built in Docker) on every variant with London weather.
# Usage: bash run_hem.sh <HEM repo> <inputs folder>     (needs Docker Desktop running; builds the image the first time)
set -e
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: keep /app and /in as container paths
REPO="$1"; IN="$2"
docker image inspect hem-engine >/dev/null 2>&1 || docker build -t hem-engine "$REPO"
docker run --rm -v "$(cygpath -w "$REPO"):/app" -v "$(cygpath -w "$IN"):/in" -v "$(cygpath -w "${WEATHER_DIR:-$REPO}"):/weather" -e EPW="${EPW_IN:-}" -w /app hem-engine bash -c '
  cargo build --release --features=clap && for f in /in/variant_*.json; do
    ./target/release/hem "$f" -e ${EPW:-examples/weather_data/London_weather_EnergyPlus_format.epw} || echo "FAILED $f"; done'
