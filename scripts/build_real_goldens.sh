#!/usr/bin/env bash
# Run miRanda / RNAhybrid / pita_prediction.pl on the bioinformatics server
# (stark08), pull the raw outputs back to tests/golden/real/, and re-run
# pytest locally so the parsers are validated against actual tool output.
#
# This server uses **password** auth (the only one of our hosts that does).
# The password is stored in /home/nee/.openclaw/workspace/CHEATSHEET.md;
# extract it once and export SSHPASS before running this script, e.g.:
#
#   export SSHPASS=$(awk '/SSHClient.*connect|client\.connect/ {print}' \
#       /home/nee/.openclaw/workspace/CHEATSHEET.md \
#       | grep -oE "'[^']{6,}'" | sed -n '4p' | tr -d "'")
#   bash scripts/build_real_goldens.sh

set -euo pipefail

: "${SSHPASS:?Set SSHPASS=<server password> before running. See header comment.}"

SSH_HOST="t150541@biotrainee.cn"
SSH_PORT="9901"
SSH_OPTS=(
  -p "${SSH_PORT}"
  -o StrictHostKeyChecking=no
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -o ConnectTimeout=15
)
SCP_OPTS=(
  -P "${SSH_PORT}"
  -o StrictHostKeyChecking=no
  -o PreferredAuthentications=password
  -o PubkeyAuthentication=no
  -o ConnectTimeout=15
)

REMOTE_WORK="/home/data/t150541/srna_win_target_validation"
LOCAL_REPO="/home/nee/srna-win-target"

# 1. Push example inputs (miRNA + targets FASTA).
sshpass -e ssh "${SSH_OPTS[@]}" "${SSH_HOST}" \
  "mkdir -p ${REMOTE_WORK}/inputs ${REMOTE_WORK}/results"
sshpass -e scp "${SCP_OPTS[@]}" \
  "${LOCAL_REPO}/examples/input/mirna.fa" \
  "${LOCAL_REPO}/examples/input/targets.fa" \
  "${SSH_HOST}:${REMOTE_WORK}/inputs/"

# 2. Run the three predictors inside conda env miRNA on the server.
sshpass -e ssh "${SSH_OPTS[@]}" "${SSH_HOST}" bash -s <<'REMOTE'
set -uo pipefail
WORK=/home/data/t150541/srna_win_target_validation
cd "${WORK}"
source /home/data/t150541/miniconda3/etc/profile.d/conda.sh
conda activate miRNA

# RNA -> DNA copies for tools that expect T-alphabet input. Only sequence
# lines are converted; header lines (starting with '>') are left intact so
# IDs like 'gene_3utr' do not become 'gene_3ttr'.
awk '/^>/ {print; next} {gsub(/[Uu]/, "T"); print}' inputs/mirna.fa  > inputs/mirna.dna.fa
awk '/^>/ {print; next} {gsub(/[Uu]/, "T"); print}' inputs/targets.fa > inputs/targets.dna.fa

echo "=== miRanda 3.3a ==="
miranda inputs/mirna.dna.fa inputs/targets.dna.fa -sc 100 -en -10 \
  -out results/miranda.out 2> results/miranda.stderr
echo "rc=$? lines=$(wc -l < results/miranda.out)"

echo "=== RNAhybrid 2.1.2 (-c -s 3utr_human) ==="
RNAhybrid -c -s 3utr_human -e -10 -p 1.0 \
  -t inputs/targets.dna.fa -q inputs/mirna.dna.fa \
  > results/rnahybrid.out 2> results/rnahybrid.stderr
echo "rc=$? lines=$(wc -l < results/rnahybrid.out)"

echo "=== pita_prediction.pl ==="
PITA_SCRIPT=/home/data/t150541/mirna/pita_prediction.pl
( cd results && perl "${PITA_SCRIPT}" -mir ../inputs/mirna.fa -utr ../inputs/targets.fa -prefix pita ) \
  2> results/pita.stderr
echo "rc=$?"
ls -la results/
REMOTE

# 3. Pull the raw outputs back into tests/golden/real/.
mkdir -p "${LOCAL_REPO}/tests/golden/real/miranda" \
         "${LOCAL_REPO}/tests/golden/real/rnahybrid" \
         "${LOCAL_REPO}/tests/golden/real/pita"
sshpass -e scp "${SCP_OPTS[@]}" \
  "${SSH_HOST}:${REMOTE_WORK}/results/miranda.out" \
  "${LOCAL_REPO}/tests/golden/real/miranda/sample.out"
sshpass -e scp "${SCP_OPTS[@]}" \
  "${SSH_HOST}:${REMOTE_WORK}/results/rnahybrid.out" \
  "${LOCAL_REPO}/tests/golden/real/rnahybrid/sample.txt"
sshpass -e scp "${SCP_OPTS[@]}" \
  "${SSH_HOST}:${REMOTE_WORK}/results/pita_pita_results.tab" \
  "${LOCAL_REPO}/tests/golden/real/pita/sample_pita_results.tab"

echo "Pulled real golden outputs to ${LOCAL_REPO}/tests/golden/real/"
echo "Now run: cd ${LOCAL_REPO} && PYTHONPATH=src python -m pytest tests/ -q"
