#!/bin/bash
cd /home/deploy/site
/home/deploy/site/venv/bin/uvicorn app.main:app --port 9999 --host 0.0.0.0
