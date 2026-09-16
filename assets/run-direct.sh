#!/usr/bin/env bash
# User parameters: fill with verified values before review. Personal Linux PC only.
RUN_DIR=''
MPIEXEC=''
VASP_EXECUTABLE=''
MPI_RANKS=''
OMP_THREADS=''
MAX_SECONDS=''
# Put only reviewed, site-specific module/source initialization below this line.

set -euo pipefail
umask 077
[[ $RUN_DIR = /* && $MPIEXEC = /* && $VASP_EXECUTABLE = /* ]] || { echo 'Set absolute paths' >&2; exit 2; }
for value in "$MPI_RANKS" "$OMP_THREADS" "$MAX_SECONDS"; do
    [[ $value =~ ^[1-9][0-9]{0,7}$ ]] || { echo 'Set positive resource/time limits' >&2; exit 2; }
done
[[ -x $MPIEXEC && -x $VASP_EXECUTABLE ]] || { echo 'Missing executable' >&2; exit 2; }
command -v timeout >/dev/null || { echo 'GNU timeout is required' >&2; exit 2; }
cd -P -- "$RUN_DIR"
for file in POSCAR INCAR POTCAR; do
    [[ -s $file && ! -L $file ]] || { echo "Missing/unsafe input: $file" >&2; exit 2; }
done
# KPOINTS/KSPACING and scientific validity must have passed the workflow's review.
for file in OUTCAR OSZICAR vasprun.xml vasp.stdout.log vasp.stderr.log; do
    [[ ! -e $file && ! -L $file ]] || { echo "Existing output: $file; use a new run directory" >&2; exit 2; }
done
mkdir -- .vaspflow-started || { echo 'Already started or launch outcome unknown; reconcile before retry' >&2; exit 3; }
# Persistent, atomic marker: never remove automatically, including on failure.
printf '%s\n' "$$" > .vaspflow-started/pid
ps -p "$$" -o lstart= > .vaspflow-started/process-start
pwd -P > .vaspflow-started/workdir
date -u +%FT%TZ > .vaspflow-started/launched-at
trap 'rc=$?; printf "%s\n" "$rc" > .vaspflow-started/exit-code' EXIT
export OMP_NUM_THREADS="$OMP_THREADS"
set +e
timeout --signal=TERM --kill-after=60s "${MAX_SECONDS}s" \
    "$MPIEXEC" -np "$MPI_RANKS" "$VASP_EXECUTABLE" > vasp.stdout.log 2> vasp.stderr.log
rc=$?
exit "$rc"
