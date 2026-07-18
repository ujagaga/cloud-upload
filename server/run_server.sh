#!/usr/bin/env bash

SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd $SCRIPT_DIR

source .venv/bin/activate
gunicorn -w 1 -b 0.0.0.0:8010 index:application
