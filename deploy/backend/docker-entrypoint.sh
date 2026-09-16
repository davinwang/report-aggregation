#!/bin/sh
# Container entrypoint: serve the API.
# When using a bind-mounted SQLite from a Windows host, WAL/SHM companion files
# may be incompatible with Linux. Checkpoint and remove them before starting.
set -e

DB_FILE="/srv/data/srp.sqlite3"

if [ -f "$DB_FILE" ]; then
  # Checkpoint any pending WAL writes into the main DB file.
  python3 -c "
import sqlite3, os
conn = sqlite3.connect('$DB_FILE')
conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
conn.execute('PRAGMA journal_mode=DELETE')
conn.close()
" 2>/dev/null || true

  # Remove leftover WAL/SHM files (may be Windows-incompatible).
  rm -f "${DB_FILE}-wal" "${DB_FILE}-shm" 2>/dev/null || true
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
