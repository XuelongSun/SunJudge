#!/usr/bin/env bash
# Run as root on Ubuntu (MySQL root uses local socket authentication).
set -euo pipefail
umask 077
exec 9>/run/lock/sunjudge-backup.lock
flock -n 9 || exit 1
backup_root=/var/backups/sunjudge
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup_root/daily" "$backup_root/weekly"
staging=$(mktemp -d "$backup_root/.pending.XXXXXX")
mysqldump --single-transaction --quick --no-tablespaces sunjudge | gzip > "$staging/database.sql.gz"
tar -C /var/lib/sunjudge -czf "$staging/uploads.tar.gz" uploads
gzip -t "$staging/database.sql.gz"
tar -tzf "$staging/uploads.tar.gz" >/dev/null
mv "$staging" "$backup_root/daily/$stamp"
if [[ $(date -u +%u) == 7 ]]; then
    cp -a "$backup_root/daily/$stamp" "$backup_root/weekly/$stamp"
fi
printf 'Backup completed: %s\n' "$backup_root/daily/$stamp"
# No automatic deletion: validate off-host copies before applying retention.
