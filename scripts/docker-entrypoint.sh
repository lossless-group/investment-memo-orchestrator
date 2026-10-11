#!/bin/sh
# Container entrypoint: make sure the workspace root exists on the volume and
# belongs to the unprivileged user, then run uvicorn as that user on $PORT.
#
# Railway mounts volumes owned by root, so the container starts as root only
# long enough to create and chown MEMO_IO_ROOT (and the local bucket root, if
# one is used), then drops to `memopop`. Behind Railway's proxy, uvicorn
# honours X-Forwarded-*; every URL MemoPop publishes still comes from
# MEMOPOP_PUBLIC_BASE_URL, never from the request.
set -eu

IO_ROOT="${MEMO_IO_ROOT:-/data/firms}"
mkdir -p "$IO_ROOT"
DIRS="$IO_ROOT"
if [ -n "${MEMOPOP_BUCKET_LOCAL_ROOT:-}" ]; then
  mkdir -p "$MEMOPOP_BUCKET_LOCAL_ROOT"
  DIRS="$DIRS $MEMOPOP_BUCKET_LOCAL_ROOT"
fi

if [ "$(id -u)" = "0" ]; then
  for d in $DIRS; do
    # Only walk the tree when ownership is wrong (a fresh volume, or files a
    # root shell left behind); a large volume is not re-chowned every boot.
    if [ "$(stat -c %U "$d")" != "memopop" ] || \
       [ -n "$(find "$d" -not -user memopop -print -quit 2>/dev/null)" ]; then
      chown -R memopop:memopop "$d"
    fi
  done
  # The parent of the workspace root holds the default local buckets.
  chown memopop:memopop "$(dirname "$IO_ROOT")"
  exec setpriv --reuid=memopop --regid=memopop --init-groups \
    env HOME=/home/memopop \
    uvicorn --factory src.connector.serve:create_app \
      --host 0.0.0.0 --port "${PORT:-8080}" \
      --proxy-headers --forwarded-allow-ips='*' --no-server-header
fi

exec uvicorn --factory src.connector.serve:create_app \
  --host 0.0.0.0 --port "${PORT:-8080}" \
  --proxy-headers --forwarded-allow-ips='*' --no-server-header
