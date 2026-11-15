# Shared VPS deployment

This deployment uses the user-requested `/home/owais/NASA_Space_App` on Ubuntu 24.04 / Python 3.12. It adapts the administrator-oriented `/opt` example without changing existing projects. The `owais` account has no sudo privileges. Existing Nginx configuration, root PM2 processes, ports and firewall rules are left untouched.

Deployment completed on 2026-11-15. All 718 project files were verified against their local SHA-256 values, all 10 model files match, Linux tests passed 37/37, and the 67-file production release verified successfully. Public Chrome QA passed all six viewport/motion combinations. Both cached/BM25 and live hybrid modes passed four-client checks; the final mode is live hybrid. Actual application rollback was exercised and the final release restored. Source-file verification precedes the small, separately recorded handoff-document updates.

- Application: `http://169.58.54.125:8097`; TCP 8097 was unused and externally reachable during preflight.
- Process: `nasa-space-app`, one Python worker, two encoder threads.
- PM2 home: `/home/owais/NASA_Space_App/.pm2`, independent of `/root/.pm2` and `/home/owais/.pm2`.
- Python environment: `/home/owais/NASA_Space_App/.venv`, rebuilt with the serving lock on Linux. `logs/dependencies.log` records installation and `pip check`.
- Runtime release: `current` points to an immutable directory in `releases/`.
- Credentials: `shared/flameledger.env`, mode 0600, outside the served frontend. Root `.env` points to it for manual commands. No SSH password is stored in the project.
- Project sources: the original plan, uploaded model artifacts, data, code, evaluation, documentation and build outputs are copied with a complete SHA-256 manifest. Windows virtualenv, interpreter/test caches and duplicate distribution archives are excluded. Public baseline weights are fetched at the original pinned revision and SHA-256 verified. Original tuned full and baseline text weights are restored only through locally byte-verified tensor recipes, then whole-file hashes must match the local originals. This changes transfer mechanics, not model contents.

Use the isolated daemon for every management command:

```bash
cd /home/owais/NASA_Space_App
export PM2_HOME=/home/owais/NASA_Space_App/.pm2
pm2 status
pm2 logs nasa-space-app --lines 50 --nostream
pm2 restart nasa-space-app --update-env
```

After adding `GEMINI_API_KEY` and `GEMINI_MODEL` to `shared/flameledger.env`, restart the application. Do not place credentials in the PM2 ecosystem file. Without these fields the evidence-template fallback remains available.

Activation and rollback operate only on this application:

```bash
bash deploy/activate-user-release.sh RELEASE_NAME
bash deploy/rollback-user-release.sh
curl --fail http://127.0.0.1:8097/api/readyz
```

An `@reboot` entry in the `owais` user's crontab restores only the dedicated project's PM2 dump. Existing crontab entries are preserved. No host reboot is performed because other projects are running.

Direct IP access uses HTTP. A DNS hostname and administrator access are still needed to add an isolated HTTPS reverse-proxy site to the existing Nginx installation. No HTTPS, live Gemini result, independent human scientific review or tested host reboot is claimed by this deployment.

The PM2 isolation follows its [multiple-runtime documentation](https://pm2.io/docs/runtime/features/multiple-pm2/); the process settings follow the [ecosystem reference](https://doc.pm2.io/en/runtime/reference/ecosystem-file/).
