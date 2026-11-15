// Dedicated PM2_HOME is required; never run this against the shared root daemon.
const root = '/home/owais/NASA_Space_App';
module.exports = {
  apps: [{
    name: 'nasa-space-app',
    namespace: 'nasa-space-app',
    cwd: `${root}/current`,
    script: `${root}/.venv/bin/python`,
    args: `-m uvicorn backend.main:app --host 0.0.0.0 --port 8097 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1 --limit-concurrency 64 --timeout-keep-alive 5 --env-file ${root}/shared/flameledger.env`,
    interpreter: 'none',
    exec_mode: 'fork',
    instances: 1,
    autorestart: true,
    watch: false,
    min_uptime: 10000,
    max_restarts: 5,
    restart_delay: 5000,
    kill_timeout: 30000,
    max_memory_restart: '2600M',
    out_file: `${root}/logs/application.log`,
    error_file: `${root}/logs/application-error.log`,
    time: true,
    env: {
      PYTHONUNBUFFERED: '1',
      PYTHONDONTWRITEBYTECODE: '1',
      HF_HUB_OFFLINE: '1',
      TRANSFORMERS_OFFLINE: '1',
      TOKENIZERS_PARALLELISM: 'false',
      OMP_NUM_THREADS: '2',
      MKL_NUM_THREADS: '2',
    },
  }],
};
