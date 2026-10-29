# Review analysis pipeline

Scripts supporting a systematic review and bibliometric analysis: record import and de-duplication, screening,
bibliometric indicators, keyword and co-authorship networks, and figure and table generation.

## Setup

    pip install -r requirements.txt
    cp local_settings.example.py local_settings.py   # add your own paths and API keys

`requirements-ml.txt` lists the optional packages for the machine-assisted extraction stage (separate environment).

## Run

    python run_all.py

Inputs and outputs are kept outside the repository.
