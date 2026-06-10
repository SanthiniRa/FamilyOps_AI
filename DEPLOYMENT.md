# Deployment

## Local Docker Stack

This repo now includes a Docker Compose stack that runs:

- Frontend on `http://localhost:5000`
- Backend API on `http://localhost:8000`
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- Qdrant on `localhost:6333`

### Start the stack

1. Copy the backend environment template:

```sh
cp backend/.env.example backend/.env
```

2. Fill in the secrets and API keys you want to use.

3. Start everything:

```sh
docker compose up --build
```

## Production Notes

- The frontend image is built with `BACKEND_URL=http://backend:8000` so the Next.js rewrites point at the API container during the image build.
- The backend image expects `DATABASE_URL`, `SECRET_KEY`, and any API keys you need in `backend/.env` or your deployment platform.
- When Redis is available in the deployment environment, set `ENABLE_SHARED_RESILIENCE_REDIS=true` so cache and rate limiting are shared across workers and replicas.
- For cloud deployment, point `DATABASE_URL` at your managed Postgres instance and set `REDIS_URL` and `QDRANT_URL` to managed or containerized equivalents.
- If you split the frontend and backend onto different hosts, update the frontend `BACKEND_URL` build argument to the public backend URL before building the image.
