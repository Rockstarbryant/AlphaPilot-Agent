#!/usr/bin/env bash
# Clean-install verification, per the hackathon spec's own checklist (#81).
# Run this from the repo root against a fresh checkout to prove the app
# doesn't depend on this machine's hidden state.
set -euo pipefail

echo "== AlphaPilot clean-install check =="

if [ ! -f .env ]; then
  cp .env.example .env
  echo "-- copied .env.example -> .env (edit JWT_SECRET before real use)"
fi

echo "-- starting postgres --"
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U alphapilot > /dev/null 2>&1; do sleep 1; done

echo "-- backend: installing deps --"
cd backend
pip install -r requirements.txt --break-system-packages --quiet

echo "-- backend: running migrations --"
export DATABASE_URL="postgresql+asyncpg://alphapilot:alphapilot@localhost:5432/alphapilot"
python -m alembic upgrade head

echo "-- backend: running tests --"
pytest tests/ -q

echo "-- frontend: installing deps --"
cd ../frontend
npm install --silent

echo "-- frontend: production build --"
npm run build

echo "== Clean-install check passed. =="
echo "Start the backend:  cd backend && uvicorn app.main:app --reload"
echo "Start the scheduler: cd backend && python -m app.jobs.scheduler"
echo "Start the frontend: cd frontend && npm run dev"
