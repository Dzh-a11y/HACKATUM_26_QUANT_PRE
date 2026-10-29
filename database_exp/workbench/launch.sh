#!/bin/sh
set -eu
LAB_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LAB_PYTHON=${WORKBENCH_PYTHON:-"$LAB_DIR/../duckdb_parquet/.venv/bin/python"}
exec "$LAB_PYTHON" "$LAB_DIR/app.py" "$@"
