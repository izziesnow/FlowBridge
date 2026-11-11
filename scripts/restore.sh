#!/bin/sh
# Restore a Flowbridge backup made by backup.sh (NFR08).
#
#   restore.sh /backups/flowbridge-YYYYMMDD-HHMMSS
#
# 1. Checks both files against SHA256SUMS and stops if either has changed.
# 2. Replaces the database contents with the dump (pg_restore --clean).
# 3. Replaces the private document store with the archive.
# Stop the web and scheduler services first, then run
# "python manage.py verify_integrity" once the restore finishes.
set -eu

SOURCE="${1:?Usage: restore.sh /path/to/flowbridge-YYYYMMDD-HHMMSS}"
MEDIA_DIR="${PRIVATE_MEDIA_ROOT:-/app/private_media}"

[ -f "$SOURCE/db.dump" ] || { echo "No db.dump in $SOURCE" >&2; exit 1; }
echo "Checking backup checksums"
(cd "$SOURCE" && sha256sum -c SHA256SUMS)

echo "Restoring database $PGDATABASE on $PGHOST"
pg_restore --clean --if-exists --no-owner --single-transaction --dbname="$PGDATABASE" "$SOURCE/db.dump"

echo "Restoring documents into $MEDIA_DIR"
mkdir -p "$MEDIA_DIR"
find "$MEDIA_DIR" -mindepth 1 -delete
tar -xzf "$SOURCE/media.tar.gz" -C "$MEDIA_DIR"

echo "Restore complete from $SOURCE. Now run: python manage.py verify_integrity"
