#!/usr/bin/env bash
set -euo pipefail
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
mkdir -p workspace/searches workspace/assets workspace/jobs
echo "RecapForge DVIDS starter is ready."
echo "Next: set DVIDS_API_KEY, then run: python -m recapforge search --query 'F-35' --types video image --limit 10"
