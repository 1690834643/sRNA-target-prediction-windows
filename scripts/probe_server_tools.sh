#!/usr/bin/env bash
# Probe miRanda / RNAhybrid / PITA / IntaRNA on the stark08 bioinformatics
# server. Requires SSHPASS to be exported (this is the password-auth host).
#
#   export SSHPASS=$(awk '/SSHClient.*connect|client\.connect/ {print}' \
#       /home/nee/.openclaw/workspace/CHEATSHEET.md \
#       | grep -oE "'[^']{6,}'" | sed -n '4p' | tr -d "'")
#   bash scripts/probe_server_tools.sh

set -u
: "${SSHPASS:?Set SSHPASS=<server password>. See header comment.}"

SSH_HOST="t150541@biotrainee.cn"
SSH_PORT="9901"

sshpass -e ssh -p "${SSH_PORT}" \
  -o StrictHostKeyChecking=no \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o ConnectTimeout=10 \
  "${SSH_HOST}" '
echo "## hostname";   hostname
echo "## conda envs"; ls /home/data/t150541/miniconda3/envs/ 2>/dev/null
echo
for tool in miranda RNAhybrid pita_prediction.pl IntaRNA; do
  echo "## ${tool}"
  for env_bin in /home/data/t150541/miniconda3/bin /home/data/t150541/miniconda3/envs/*/bin; do
    if [ -x "${env_bin}/${tool}" ]; then echo "  found: ${env_bin}/${tool}"; fi
  done
  if which "${tool}" >/dev/null 2>&1; then echo "  PATH:  $(which ${tool})"; fi
done
echo
echo "## known PITA script location"
find /home/data/t150541 -maxdepth 5 -name "pita_prediction.pl" 2>/dev/null
'
