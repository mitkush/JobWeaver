#!/usr/bin/env bash
# Oracle downloads the image over HTTPS. The run-scoped token arrives on stdin.
set -euo pipefail
umask 077

remote_dir=${1:?Usage: download-deploy-image.sh DIRECTORY REPOSITORY ARTIFACT_ID SHA256}
repository=${2:?Missing repository}
artifact_id=${3:?Missing artifact id}
expected_sha=${4:?Missing image checksum}
[[ "$repository" =~ ^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$ ]]
[[ "$artifact_id" =~ ^[0-9]+$ ]]
[[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]]
IFS= read -r artifact_token
test -n "$artifact_token"
cd "$remote_dir"
trap 'rm -f image.zip jobweaver-image.tar.gz.part' EXIT

# Keep credentials out of process arguments and files. curl does not forward the
# Authorization header to the artifact storage host on a cross-host redirect.
printf 'header = "Authorization: Bearer %s"\n' "$artifact_token" |
  curl --config - --fail --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 20 --max-time 600 --retry 2 --retry-delay 5 --retry-max-time 660 \
    --speed-limit 1024 --speed-time 60 --output image.zip \
    "https://api.github.com/repos/$repository/actions/artifacts/$artifact_id/zip"
unset artifact_token

python3 - "$expected_sha" <<'PY'
import hashlib
import sys
import zipfile

digest = hashlib.sha256()
with zipfile.ZipFile("image.zip") as archive:
    if archive.namelist() != ["jobweaver-image.tar.gz"]:
        raise SystemExit("Unexpected deployment artifact contents")
    with archive.open("jobweaver-image.tar.gz") as source:
        with open("jobweaver-image.tar.gz.part", "wb") as destination:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                destination.write(chunk)
if digest.hexdigest() != sys.argv[1]:
    raise SystemExit("Deployment image checksum mismatch")
PY
mv jobweaver-image.tar.gz.part jobweaver-image.tar.gz
echo 'Production image downloaded and checksum verified.'
