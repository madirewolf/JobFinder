# Running JobFinder locally

Step-by-step guide to start the tracker UI and database on your machine.

---

## Every time (normal use)

**1. Start Docker Desktop**  
Wait until Docker reports it is running.

**2. Start Postgres**

```powershell
cd c:\Users\moham\Desktop\Projects\JobFinder
docker compose up -d postgres
```

**3. Start the web UI**

```powershell
cd c:\Users\moham\Desktop\Projects\JobFinder
uv run jfb web serve --port 8000
```

**4. Open in your browser:** http://127.0.0.1:8000  

Stop the server with **Ctrl+C** in that terminal.

---

## First time on a new machine (one-time setup)

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv), Docker Desktop.

```powershell
cd c:\Users\moham\Desktop\Projects\JobFinder
copy .env.example .env
# Edit .env if needed (DATABASE_URL, API keys for classify/draft)
uv sync --extra dev
docker compose up -d postgres
uv run alembic upgrade head
uv run jfb seed load
```

Then follow **Every time** above.

On Linux/macOS you can use `make bootstrap` instead of the last four commands after copying `.env`.

---

## Optional: refresh job data

```powershell
uv run jfb ingest all
uv run jfb classify all
uv run jfb top --limit 30
```

---

## Quick checks

| What | How |
|------|-----|
| Postgres running? | `docker ps` — look for `jfb-postgres` |
| DB summary | `uv run jfb stats` |
| App health | http://127.0.0.1:8000/healthz |

---

## Troubleshooting

- **Docker errors** — Start Docker Desktop and wait ~30s, then run `docker compose up -d postgres` again.
- **Port 5432 in use** — Another Postgres may be running; stop it or change the port in `docker-compose.yml` and `DATABASE_URL` in `.env`.
- **Windows web server** — Always use `uv run jfb web serve` (not raw uvicorn); the CLI sets the correct event loop for psycopg.

---

## Cheat sheet

```
Docker on → docker compose up -d postgres → uv run jfb web serve --port 8000 → http://127.0.0.1:8000
```
