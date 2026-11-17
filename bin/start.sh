#!/bin/sh
# Production start (Render runs this via the Dockerfile's prod target).
set -e

python manage.py migrate --noinput
python manage.py createcachetable
# The law text ships in data/corpus.json; loading is idempotent and takes a second or two.
python manage.py load_corpus

# With an AI key, embed any passages that have no vector yet. In the background so a slow or
# rate-limited API never blocks the web server; it resumes where it stopped on the next start.
if [ -n "$GEMINI_API_KEY" ]; then
  (python manage.py embed_corpus || echo "Embedding paused; keyword search still works.") &
fi

# Threads, not processes: the free instance has 512 MB. Access log without query strings
# (questions can contain personal details).
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 --worker-class gthread --threads 4 \
  --worker-tmp-dir /dev/shm \
  --max-requests 1000 --max-requests-jitter 100 \
  --timeout 60 --graceful-timeout 30 \
  --access-logfile - --access-logformat '%(h)s "%(m)s %(U)s" %(s)s %(b)s %(L)s'
