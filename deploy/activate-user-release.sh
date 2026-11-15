#!/usr/bin/env bash
# Isolated unprivileged deployment for the supplied shared VPS.
set -euo pipefail
base=/home/owais/NASA_Space_App
export PM2_HOME="$base/.pm2"
name=${1:?Usage: activate-user-release.sh RELEASE_NAME}
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Invalid release name'; exit 2; }
candidate=$(realpath "$base/releases/$name")
[[ "$candidate" == "$base/releases/"* && -f "$candidate/release.json" ]] || exit 2
[[ $(df -Pm "$base" | awk 'NR==2 {print $4}') -ge 5120 ]] || { echo 'Insufficient free disk'; exit 2; }
( cd "$candidate" && "$base/.venv/bin/python" -m scripts.verify_release --release "$candidate" )
prior=$(readlink -f "$base/current" || true)
restore() {
    echo 'Activation failed; restoring prior application pointer'
    if [[ "$prior" == "$base/releases/"* && -d "$prior" ]]; then
        ln -sfn "$prior" "$base/current.next"
        mv -Tf "$base/current.next" "$base/current"
        pm2 startOrRestart "$base/deploy/ecosystem.config.cjs" --only nasa-space-app --update-env
    else
        pm2 stop nasa-space-app || true
    fi
}
trap restore ERR
ln -sfn "$candidate" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
pm2 startOrRestart "$base/deploy/ecosystem.config.cjs" --only nasa-space-app --update-env
ready=0
for attempt in $(seq 1 90); do
    if curl --silent --fail http://127.0.0.1:8097/api/readyz >/dev/null; then ready=1; break; fi
    sleep 1
done
(( ready == 1 ))
curl --silent --fail -H 'Content-Type: application/json' -d '{"preset_id":"lunar"}' http://127.0.0.1:8097/api/scenario >/dev/null
if [[ "$prior" == "$base/releases/"* && "$prior" != "$candidate" ]]; then
    ln -sfn "$prior" "$base/previous"
fi
pm2 save
trap - ERR
echo "Activated $name on port 8097 in the project-specific PM2 daemon."
