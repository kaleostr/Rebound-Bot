#!/usr/bin/env bash
set -e
export PYTHONUNBUFFERED=1
python3 -m uvicorn main:app --host 0.0.0.0 --port 8099 --root-path "${INGRESS_ENTRY:-}" --proxy-headers
