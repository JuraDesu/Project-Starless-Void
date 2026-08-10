#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_cmd="${PYTHON:-python3}"
exec "$python_cmd" "$project_root/engine/sdk/tools/build_content_project.py" "$@" --project "$project_root"
