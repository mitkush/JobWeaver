#!/usr/bin/env bash
# Run on the Oracle VM after uploading a built image. Secrets stay in backend/.env.
set -Eeuo pipefail

archive=${1:?Usage: deploy-oracle.sh IMAGE_ARCHIVE COMMIT}
commit=${2:?Usage: deploy-oracle.sh IMAGE_ARCHIVE COMMIT}
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid commit'; exit 1; }
cd /home/ubuntu/JobWeaver
exec 9>/home/ubuntu/.jobweaver-deploy.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
test -f backend/.env
sudo -n docker info >/dev/null
db_network=jobweaver-net
db_container=jobweaver-postgres
sudo -n docker network inspect "$db_network" >/dev/null || {
  echo "Required Docker network $db_network is missing"; exit 1;
}
db_running=$(sudo -n docker inspect --format '{{.State.Running}}' "$db_container" 2>/dev/null || true)
test "$db_running" = true || {
  echo "Required PostgreSQL container $db_container is not running"; exit 1;
}
sudo -n docker exec "$db_container" pg_isready -U jobweaver -d jobweaver >/dev/null || {
  echo "PostgreSQL container $db_container is not ready"; exit 1;
}
git diff --quiet
git diff --cached --quiet
test "$(git branch --show-current)" = main
git fetch origin main
test "$(git rev-parse origin/main)" = "$commit" || {
  echo 'Main changed since this build. Run the workflow again.'; exit 1;
}
git merge --ff-only "$commit"
sudo -n docker load -i "$archive"
sudo -n docker image inspect "jobweaver:$commit" >/dev/null

previous=false
rollback() {
  status=$?
  trap - ERR
  echo 'Deployment failed; restoring the previous container when available.'
  sudo -n docker logs --tail 50 jobweaver 2>&1 || true
  sudo -n docker rm -f jobweaver >/dev/null 2>&1 || true
  if "$previous"; then
    sudo -n docker rename jobweaver-previous jobweaver
    sudo -n docker start jobweaver
  fi
  exit "$status"
}

# Keep the current container and its exact environment for recovery.
if sudo -n docker container inspect jobweaver >/dev/null 2>&1; then
  if sudo -n docker container inspect jobweaver-previous >/dev/null 2>&1; then
    sudo -n docker rm jobweaver-previous >/dev/null
  fi
  sudo -n docker stop jobweaver
  sudo -n docker rename jobweaver jobweaver-previous
  previous=true
fi
trap rollback ERR
sudo -n docker run -d \
  --name jobweaver --restart unless-stopped \
  --network "$db_network" \
  --env-file backend/.env -p 127.0.0.1:8000:8000 \
  --log-opt max-size=10m --log-opt max-file=3 \
  --label "org.opencontainers.image.revision=$commit" \
  "jobweaver:$commit"

healthy=false
for attempt in {1..60}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null; then
    healthy=true
    break
  fi
  sleep 2
done
"$healthy" || { echo 'Application failed its health check'; false; }
# Apply new Feed rules to stored jobs without requiring each user to save Preferences.
sudo -n docker exec -i jobweaver python - <<'PY'
import asyncio
from app.core.db import get_sessionmaker
from app.services.feed import sync_all_feeds

async def main():
    async with get_sessionmaker()() as session:
        await sync_all_feeds(session)
        await session.commit()

asyncio.run(main())
PY
sudo -n docker tag "jobweaver:$commit" jobweaver:production
trap - ERR
rm -f "$archive"
echo "Deployed $commit successfully. Previous container retained for recovery."
