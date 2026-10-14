# Deploy JobWeaver from GitHub

Production runs on the Oracle Ubuntu VM at `92.4.68.22`. Caddy serves
`https://jobweaver.duckdns.org`; Docker serves the app on localhost port 8000.
The database and provider credentials remain in `/home/ubuntu/JobWeaver/backend/.env`.

## One-time setup

In GitHub, open **Settings → Secrets and variables → Actions → New repository secret**.
Add:

- `ORACLE_SSH_PRIVATE_KEY`: the complete contents of your Oracle SSH private key
  (`~/Downloads/ssh-key-2026-10-07.key`). Paste directly into GitHub, not a commit or chat.
- `ORACLE_KNOWN_HOSTS`: the server entry already trusted by your Mac's SSH client.
  In your Mac terminal, run `ssh-keygen -F 92.4.68.22` and copy its host-key lines,
  excluding comment lines. If no entry exists, verify the server fingerprint first.

The workflow defaults to host `92.4.68.22`. If it changes, set repository variable
`ORACLE_HOST`, update the verified host entry and DuckDNS.

The VM must have Docker, git, curl and flock. The ubuntu account must already have
noninteractive sudo access to Docker. The repo must be on main with no tracked edits,
and its GitHub credentials must still allow fetching origin. These match the existing setup.

## Deploy

1. Merge the update into main and wait for its **CI** workflow to pass.
2. Open **Actions → Deploy to Oracle → Run workflow**, selecting main.
3. Wait for the workflow to finish. Open the website and refresh the browser.

Or run on your Mac:

```bash
gh workflow run deploy-oracle.yml --repo mitkush/JobWeaver --ref main
```

GitHub builds the image and pushes it to the private GitHub Container Registry
(`ghcr.io/mitkush/jobweaver`, tagged with the commit). Over a verified SSH connection,
the VM then pulls that exact image by digest using the run's short-lived token, so Docker
downloads only the layers it does not already have, and updates the VM's checkout. The
VM keeps the old app running during build and pull.
It then stops and renames the old container, starts the new one, applies migrations
through the image's normal startup command, waits for health, and rechecks stored Feed
matches. The image is tagged with the exact commit; the script refuses a stale build
if main has advanced. No API credentials are copied into GitHub.

The SSH credential grants access as ubuntu, including its existing sudo permissions.
Only trusted repository maintainers should be able to edit and run this workflow.

## Recovery and limitations

If startup, local health or Feed refresh fails, the script restores the previous container
and marks the workflow failed. This restores the application container, not database
changes: migrations must remain compatible with the previous app. Back up the database
before destructive migrations. Public HTTPS failures are reported after deployment;
check Caddy and DNS if local health passed.

The stopped `jobweaver-previous` container is retained until the next deployment. To
restore it manually on Oracle:

```bash
sudo docker stop jobweaver
sudo docker rm jobweaver
sudo docker rename jobweaver-previous jobweaver
sudo docker start jobweaver
```

The action deliberately uses a button, so merging does not deploy automatically.
After a successful deploy the VM keeps the new image and the previous container's image
for recovery and removes older `jobweaver:<commit>` tags and dangling layers. GHCR keeps
the five most recent image versions; older ones are deleted by the workflow. The first
deploy after this change pulls every layer once; later deploys pull only changed layers.
The registry token is never stored on the VM: login uses a temporary Docker config that
is deleted when the pull ends.
