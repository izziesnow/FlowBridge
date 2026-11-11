#!/bin/sh
# Back up the Flowbridge database and private documents (NFR08).
#
# Creates  $BACKUP_DIR/flowbridge-YYYYMMDD-HHMMSS/  containing:
#   db.dump        PostgreSQL custom-format dump (pg_dump -Fc)
#   media.tar.gz   the private document store
#   SHA256SUMS     checksums of both files, checked again before any restore
#   manifest.txt   when, from where, and row counts for the key tables
#
# Backups older than $RETENTION_DAYS days are removed.
# Database connection settings come from the standard PG* environment variables.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
MEDIA_DIR="${PRIVATE_MEDIA_ROOT:-/app/private_media}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/flowbridge-$STAMP"

mkdir -p "$TARGET"
echo "Backing up database $PGDATABASE on $PGHOST to $TARGET"
pg_dump --format=custom --no-owner --file="$TARGET/db.dump"

if [ -d "$MEDIA_DIR" ]; then
  tar -czf "$TARGET/media.tar.gz" -C "$MEDIA_DIR" .
else
  tar -czf "$TARGET/media.tar.gz" --files-from /dev/null
fi

(cd "$TARGET" && sha256sum db.dump media.tar.gz > SHA256SUMS)

{
  echo "created_utc=$STAMP"
  echo "database=$PGDATABASE@$PGHOST"
  for table in approvals_approvalrequest approvals_revision approvals_documentversion approvals_decision audit_auditevent; do
    echo "rows.$table=$(psql -Atc "SELECT count(*) FROM $table")"
  done
} > "$TARGET/manifest.txt"

find "$BACKUP_DIR" -maxdepth 1 -type d -name 'flowbridge-*' -mtime "+$RETENTION_DAYS" -exec rm -rf {} +
echo "Backup complete: $TARGET"
cat "$TARGET/manifest.txt"
