#!/usr/bin/env bash
cd "$(dirname "$0")" && exec .venv/bin/python guardian.py --set-google-app
