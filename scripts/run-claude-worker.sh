#!/usr/bin/env bash
# Optional personal worker only. Does not edit the app's environment or restart the app.
set -euo pipefail
cd "$(dirname "$0")/.."
state_dir="${CLAUDE_CODE_STATE_DIR:-$HOME/.local/share/jobweaver-claude}"
image='python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704'
expected='356733f185fa988e6bf3aa9a555269fdd167982a2e2a80d3c8a78037bb92ad58'
test -f "$state_dir/claude"
test -f "$state_dir/worker.env"
test "$(stat -c %a "$state_dir/worker.env")" = 600
actual=$(sha256sum "$state_dir/claude")
test "${actual%% *}" = "$expected" || { echo 'CLI checksum mismatch'; exit 1; }
available_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
(( available_kib >= 320 * 1024 )) || { echo 'Not enough memory headroom for the worker'; exit 1; }
sudo -n docker network inspect jobweaver-net >/dev/null
if sudo -n docker container inspect jobweaver-claude >/dev/null 2>&1; then
  echo 'Worker already exists. Stop and remove only jobweaver-claude before replacing it.'
  exit 1
fi
cp backend/app/gateway/cli_worker.py "$state_dir/worker.py"
chmod 444 "$state_dir/worker.py"
sudo -n docker run -d --name jobweaver-claude --restart unless-stopped \
  --network jobweaver-net --memory=256m --memory-swap=256m --cpus=0.5 --pids-limit=128 \
  --read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
  --log-opt max-size=1m --log-opt max-file=2 \
  --tmpfs /work:rw,nosuid,nodev,noexec,size=32m,uid=65534,gid=65534 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=16m,uid=65534,gid=65534 \
  --workdir /work --env-file "$state_dir/worker.env" \
  --mount "type=bind,src=$state_dir/claude,dst=/opt/claude,readonly" \
  --mount "type=bind,src=$state_dir/worker.py,dst=/worker.py,readonly" \
  --entrypoint python "$image" /worker.py
# There is deliberately no host port, Docker socket, SSH, repository or DB volume mount.
