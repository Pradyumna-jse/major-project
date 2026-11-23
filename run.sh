#!/usr/bin/env bash
set -e
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python scripts/download_models.py
python app.py
