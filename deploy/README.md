# Linux VPS handoff

Target: one Linux host with 4 GB RAM, 4 vCPUs and at least 20 GB free before staging. No deployment has been performed without host access. Local Windows timing and memory do not establish VPS performance.

**Current deployed host:** the user supplied a shared Ubuntu VPS and requested `/home/owais/NASA_Space_App`. Because the account has no sudo privileges and existing projects use root PM2/Nginx, the actual deployment uses the isolated user-level configuration in [VPS.md](VPS.md), port 8097 and a project-specific PM2 home. Linux checks, public browser QA and application rollback passed. The administrator-oriented `/opt`, systemd and Caddy example below was not applied to the shared host.

1. Create an unprivileged `flameledger` service account. Create `/opt/flameledger/releases`, `/opt/flameledger/venv` and `/var/cache/flameledger`; make the cache writable by the service account. Keep release directories read-only to that account.
2. Build the model/index/frontend elsewhere and upload a complete release to `/opt/flameledger/releases/<release-name>`. The prepared archive is `build/dist/flameledger-20261115-final.tar.gz`, SHA-256 `9160152aa2cf67303817275a2392be1c950ccea876025b87ace85b3471f3611f`. Its sole top-level prefix is `flameledger/`; list and validate entries before extracting into a fresh staging directory, strip that prefix, then verify the extracted release. Preserve the current and one previous known-good release. Never upload the training archive or `.env` into the public web root. Reference base weights are deliberately excluded.
3. Create the host venv with Python 3.12. Install the tested serving lock, with CPU PyTorch first when live hybrid is needed:

   ```bash
   python3 -m venv /opt/flameledger/venv
   /opt/flameledger/venv/bin/python -m pip install torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
   /opt/flameledger/venv/bin/python -m pip install -r requirements-serving.lock
   ```

   For a lightweight cached/BM25 server, install `requirements-runtime.lock`; it does not need PyTorch. Validate Linux resolution and record `pip freeze` on the actual host. The existing lock was resolved and tested on Windows and is not a claim of Linux validation.
4. Copy `deploy/flameledger.env.example` to `/etc/flameledger.env`; set its mode to `0600`. Keep `cached_bm25` until host inference meets the budget. Set Gemini credentials only on the host. Copy `deploy/flameledger.service` into the systemd service directory, then reload systemd.
5. Install Caddy, set its `FLAMELEDGER_PUBLIC_HOSTNAME` and `ACME_EMAIL` service environment, and install the provided Caddyfile. Use a real DNS hostname pointing at the VPS. Caddy handles HTTPS, static compression and same-origin `/api` proxying.
6. Run `bash deploy/activate-release.sh <release-name>` as the host administrator. It validates the staged release before stopping the single worker, switches the symlink and checks readiness. A failure restores the prior pointer. It never starts two model workers concurrently. There must be at least 5 GiB free after staging.
7. Run `scripts.smoke_api` against the public HTTPS origin. Test the page in a private browser, both presets, pinned source PDFs, coverage selection and CSV. Repeat with an absent Gemini key, and use a fake provider in the local regression suite for timeout/invalid-output paths.

Record actual host measurements:

```bash
free -m
df -h
systemctl show flameledger -p MemoryCurrent -p MemoryPeak -p NRestarts
journalctl -u flameledger --since '10 minutes ago'
```

Measure cold startup, warm queries, four-client mixed load and one live encode if enabled. Targets: warm search p95 ≤3 s, live Gemini briefing p95 ≤10 s, about 700 MiB host headroom, at least 5 GiB free, no OOM/restarts or sustained swap. Test cached/BM25 separately from live hybrid. If live inference fails the budget, retain `cached_bm25`; a configured mode is never presented as a measured result.

Rollback with `bash deploy/rollback.sh`. It verifies `/opt/flameledger/previous` before stopping the current worker and restoring that pointer. Exercise this on the actual host and record both release IDs before a public demonstration.

The administrator-oriented activation scripts and systemd/Caddy configuration above remain unapplied. The user-level activation and rollback scripts were exercised on the supplied VPS; **https://flameledger.agenticerastudio.tech** is publicly reachable over HTTPS via an isolated Nginx server block and Let's Encrypt certificate proxying to `127.0.0.1:8097`. A locally playable venue fallback is available; verify the event's current submission format and AI-disclosure rules before submitting.
