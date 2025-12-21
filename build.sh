#!/usr/bin/env bash
source .venv/bin/activate
pip install pyinstaller
pyinstaller --onefile --noconsole main.py -n photo_burst_analyzer
