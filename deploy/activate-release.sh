#!/usr/bin/env bash
# Run as root after uploading a fully assembled release. Never runs parallel workers.
set -euo pipefail
candidate_name=${1:?Usage: activate-release.sh RELEASE_DIRECTORY_NAME}
[[ "$candidate_name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Invalid release directory name'; exit 2; }
release_root=/opt/flameledger/releases
candidate=$(realpath "$release_root/$candidate_name")
[[ "$candidate" == "$release_root/"* && -f "$candidate/release.json" ]] || { echo 'Candidate is outside releases or incomplete'; exit 2; }
available_mb=$(df -Pm "$release_root" | awk 'NR==2 {print $4}')
(( available_mb >= 5120 )) || { echo 'Keep at least 5 GiB free after staging'; exit 2; }
( cd "$candidate" && /opt/flameledger/venv/bin/python -m scripts.verify_release --release "$candidate" )
prior=$(readlink -f /opt/flameledger/current || true)
rollback() {
    echo 'Activation failed; restoring prior release'
    if [[ "$prior" == "$release_root/"* && -d "$prior" ]]; then
        systemctl stop flameledger
        ln -sfn "$prior" /opt/flameledger/current.next
        mv -Tf /opt/flameledger/current.next /opt/flameledger/current
        systemctl start flameledger
    fi
}
trap rollback ERR
systemctl stop flameledger
ln -sfn "$candidate" /opt/flameledger/current.next
mv -Tf /opt/flameledger/current.next /opt/flameledger/current
systemctl start flameledger
ready=0
for attempt in $(seq 1 60); do
    if curl --silent --fail http://127.0.0.1:8000/api/readyz >/dev/null; then ready=1; break; fi
    sleep 1
done
(( ready == 1 ))
curl --silent --fail -H 'Content-Type: application/json' -d '{"preset_id":"lunar"}' http://127.0.0.1:8000/api/scenario >/dev/null
if [[ "$prior" == "$release_root/"* && -d "$prior" ]]; then
    ln -sfn "$prior" /opt/flameledger/previous
fi
trap - ERR
echo "Activated $candidate_name. Run scripts.smoke_api, CSV export, mixed-load checks and host memory measurements before judging."
