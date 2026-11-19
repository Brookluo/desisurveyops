#!/bin/bash
#SBATCH --job-name=desi-tertiary-status
#SBATCH -A desi
#SBATCH -C cpu
#SBATCH -q shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=01:00:00
set -eo pipefail
source /global/cfs/cdirs/desi/software/desi_environment.sh 25.3
export PYTHONPATH="$PWD/py${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
outdir=${2:-/global/cfs/cdirs/desicollab/users/brookluo/tertiary-status}
page="$outdir/tertiary-status.html"
previous=$(stat -c '%d:%i' "$page" 2>/dev/null || true)

"$PWD/bin/desi_tertiary_status" --prognums "${1:?expected program numbers}" \
    --outdir "$outdir" --numproc 2

# Atomic publication installs a new inode. An old, valid page does not
# count as success for this run. Nonzero exit activates the Slurm retry.
current=$(stat -c '%d:%i' "$page")
if [[ "$current" == "$previous" || $(tail -n 1 "$page") != '</body></html>' ]]; then
    echo "Update failed to publish a new, complete $page" >&2
    exit 1
fi
echo "Published $page (job $SLURM_JOB_ID)"
