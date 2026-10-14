#!/usr/bin/env bash
# Run on the Oracle VM: pull the image GitHub pushed to GHCR, by digest, and tag it with
# its commit. Docker downloads only the layers the VM does not already have.
# The run-scoped registry token arrives on stdin and is never written outside a
# temporary Docker config that is removed on exit.
set -euo pipefail
umask 077

image=${1:?Usage: pull-deploy-image.sh IMAGE DIGEST COMMIT USER}
digest=${2:?Missing image digest}
commit=${3:?Missing commit}
user=${4:?Missing registry user}
[[ "$image" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+$ ]] || { echo 'Invalid image'; exit 1; }
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'Invalid digest'; exit 1; }
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid commit'; exit 1; }
[[ "$user" =~ ^[A-Za-z0-9-]+$ ]] || { echo 'Invalid registry user'; exit 1; }
IFS= read -r token
test -n "$token"

config=$(mktemp -d)
cleanup() { sudo -n rm -rf "$config"; }
trap cleanup EXIT
printf '%s\n' "$token" | sudo -n docker --config "$config" login ghcr.io -u "$user" --password-stdin >/dev/null
unset token
# Pulling by digest means Docker verifies every byte against what GitHub built.
sudo -n timeout 20m docker --config "$config" pull --quiet "$image@$digest"
sudo -n docker --config "$config" logout ghcr.io >/dev/null 2>&1 || true
sudo -n docker tag "$image@$digest" "jobweaver:$commit"
echo "Pulled $image@$digest as jobweaver:$commit."
