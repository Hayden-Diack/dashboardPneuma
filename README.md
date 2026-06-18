# Pneuma — Streamlit Dashboard

## Streamlit Cloud

Access and control of deployment via https://share.streamlit.io


To view site live ---> https://pneumadata.streamlit.app/


## Local quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your DB password
# File is at #####

# 3. Run
streamlit run app.py
```

The dashboard opens at **http://localhost:8501** automatically.

## Features

- **Overview** — KPI cards, map distribution, end-phase bar chart, rolling win rate trend
- **Match history** — Filterable table (win/loss, map, region)
- **Players** — Per-player stats: survival, time zones, ghost encounters, favourite rooms
- **Ghosts** — Avg hunts, possessions, appearance frequency, favourite rooms
