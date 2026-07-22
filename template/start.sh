#!/bin/bash
set -e

cd /opt/lizard-server
pip install -q -r requirements.txt
exec /usr/local/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080 --log-level warning
