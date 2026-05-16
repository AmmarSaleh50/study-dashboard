#!/usr/bin/env bash
# scripts/migrate_study_root.sh — Phase 1 one-shot ops migration.
#
# Moves /opt/courses/<COURSE>/... -> /opt/courses/<operator-uuid>/<COURSE>/...
# Idempotent via a marker file. Runs from deploy.sh after `db push`.
set -euo pipefail

STUDY_ROOT="${STUDY_ROOT:-/opt/courses}"
OP_ID="${OPERATOR_USER_ID:-00000000-0000-0000-0000-000000000001}"
MARKER="${STUDY_ROOT}/.phase1_migrated"

if [[ -f "${MARKER}" ]]; then
    echo "phase 1 FS migration already done (marker exists at ${MARKER})"
    exit 0
fi

if [[ ! -d "${STUDY_ROOT}" ]]; then
    echo "STUDY_ROOT ${STUDY_ROOT} does not exist — skipping migration"
    exit 0
fi

TARGET="${STUDY_ROOT}/${OP_ID}"
mkdir -p "${TARGET}"

# Move every top-level course folder into the operator subdirectory.
# Skip non-directories, hidden entries, and the operator folder itself.
shopt -s nullglob
for entry in "${STUDY_ROOT}"/*; do
    if [[ ! -d "${entry}" ]]; then
        continue
    fi
    base="$(basename "${entry}")"
    if [[ "${base}" == "${OP_ID}" ]]; then
        continue
    fi
    if [[ "${base}" == .* ]]; then
        continue
    fi
    echo "moving ${base} -> ${OP_ID}/${base}"
    mv "${entry}" "${TARGET}/${base}"
done
shopt -u nullglob

touch "${MARKER}"
echo "phase 1 FS migration complete (marker written to ${MARKER})"
