#!/usr/bin/env bash
set -euo pipefail
base=/home/owais/NASA_Space_App
prior=$(readlink -f "$base/previous")
[[ "$prior" == "$base/releases/"* && -f "$prior/release.json" ]] || { echo 'No prior release'; exit 2; }
exec bash "$base/deploy/activate-user-release.sh" "$(basename "$prior")"
