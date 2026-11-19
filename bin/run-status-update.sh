#!/bin/bash
# The cron allocation only submits jobs. Queue the recovery job now so it
# still runs if Slurm kills the first worker (OOM, timeout, or node loss).
set -euo pipefail
bindir=$(cd -- "$(dirname -- "$0")" && pwd)
worker="$bindir/tertiary-status-worker.sbatch"
prognums=$(<"$bindir/tertiary-progress.txt")
options=(--parsable --chdir="$bindir/.." --output="$bindir/status-worker-%j.out")
first=$(sbatch "${options[@]}" --dependency=singleton "$worker" "$prognums")
jobid=${first%%;*}
echo "Submitted tertiary update $jobid for programs $prognums"
retry=$(sbatch "${options[@]}" --dependency="afternotok:$jobid,singleton" \
    --kill-on-invalid-dep=yes "$worker" "$prognums")
echo "Queued conditional retry ${retry%%;*} for update $jobid"
