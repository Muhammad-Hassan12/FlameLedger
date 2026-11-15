#!/usr/bin/env bash
set -euo pipefail
previous=$(readlink -f /opt/flameledger/previous)
[[ "$previous" == /opt/flameledger/releases/* && -f "$previous/release.json" ]] || { echo 'No validated previous release'; exit 2; }
( cd "$previous" && /opt/flameledger/venv/bin/python -m scripts.verify_release --release "$previous" )
systemctl stop flameledger
ln -sfn "$previous" /opt/flameledger/current.next
mv -Tf /opt/flameledger/current.next /opt/flameledger/current
systemctl start flameledger
echo 'Prior release restored; verify readiness and run the smoke checks.'
