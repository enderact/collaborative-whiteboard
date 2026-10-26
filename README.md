# Real-Time Collaborative Whiteboard

BCSE406L NoSQL course project. Shared HTML5 canvas. MongoDB holds rooms, an append-only stroke log, and snapshots. Redis does sequence numbers, presence, and Pub/Sub so two Python processes stay in sync.

https://github.com/enderact/collaborative-whiteboard

## Requirements

Python 3.11 or newer (the app uses `dict | None`). Docker Desktop for MongoDB 7 (replica set `rs0`) and Redis 7. Ports 27017, 6379, and 8001 need to be free; 8002 as well if you run two app processes.

The helper scripts are PowerShell. Everything else is ordinary Python and Docker, so macOS and Linux are fine.

Start Docker Desktop (whale icon in the tray) before `docker compose`. The first pull of `mongo:7` and `redis:7-alpine` needs internet. If a local MongoDB is already bound to 27017, stop it or the container will fail to start.

## First-time setup

Clone or unzip so `docker-compose.yml` is at the top of the folder.

Windows (PowerShell):

```powershell
cd <path>\whiteboard

python --version          # 3.11 or newer
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Copy-Item .env.example .env

docker compose up -d
```

Wait until both containers are healthy:

```powershell
docker compose ps
```

`wb-mongo` and `wb-redis` should be `Up (healthy)`. `mongo-init` starts replica set `rs0` once and then exits.

Seed a large dataset (needed for analytics and the index demo; a few minutes):

```powershell
.\.venv\Scripts\python.exe scripts\seed.py --strokes 80000 --rooms 5 --wipe
```

The script prints the largest room code at the end (random 6 letters). Write that down.

Optional, so joining that huge room is fast:

```powershell
.\.venv\Scripts\python.exe scripts\make_snapshot.py --all
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
python scripts/seed.py --strokes 80000 --rooms 5 --wipe
python scripts/make_snapshot.py --all
```

`.env.example` is already set for local Docker:

```
MONGO_URI=mongodb://localhost:27017/?directConnection=true
MONGO_DB=whiteboard
REDIS_URL=redis://localhost:6379/0
SNAPSHOT_INTERVAL=500
```

`directConnection=true` is required because Compose runs a single-node replica set advertised as `localhost:27017`.

## Run the app

One server:

```powershell
cd <path>\whiteboard
docker compose up -d          # if containers are not already up
.\scripts\run.ps1             # http://127.0.0.1:8001  instance wb-1
```

Without the script:

```powershell
$env:INSTANCE_ID = "wb-1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open http://127.0.0.1:8001

Two servers, to show Redis crossing process boundaries:

```powershell
.\scripts\demo-two-instances.ps1
```

Open the same room code in two browser windows:

- http://127.0.0.1:8001  badge `wb-1`
- http://127.0.0.1:8002  badge `wb-2`

Draw in one window. Ink and cursors show up in the other through Redis Pub/Sub, not a shared Python process.

Stop both:

```powershell
.\scripts\demo-two-instances.ps1 -Stop
```

Stop the app and Docker:

```powershell
.\scripts\demo-two-instances.ps1 -Stop
docker compose down
```

`docker compose down` keeps the Mongo volume, so data is still there next `up`. Wipe the volume with `docker compose down -v`.

## Using the board

Enter a display name on the lobby. Create a board, or type a room code and join. Seeded rooms show in the recent list; use the large one for Analytics and Indexes.

Draw with pen, eraser, rectangle, ellipse, or line. Undo and redo are per user. Click the room-code chip to copy it for someone else.

Analytics runs MongoDB aggregation pipelines on the current room. The Indexes panel times the same queries with indexes vs a collection scan (`explain` COLLSCAN vs IXSCAN).

REST explorer: http://127.0.0.1:8001/docs

## Architecture

```
Browser (static/ : canvas + WebSocket)
        |
        |  HTTP REST + /ws/{roomCode}
        v
FastAPI  (one or more uvicorn processes, INSTANCE_ID = wb-1 / wb-2)
        |                          |
        | PyMongo                  | redis.asyncio
        v                          v
 MongoDB 7 replica set rs0      Redis 7
 rooms / strokes / snapshots    INCR seq, Pub/Sub, presence HASH+TTL
```

MongoDB collections:

- `rooms`: `code` (unique 6-char), title, participants, `strokeCount`, `lastActivityAt`, archive flag.
- `strokes`: one document per stroke: `roomId`, `seq`, `userId`, `tool`, `style`, `points[]`, `bbox`, `active` (false after undo), `createdAt`. Append-only; undo is a flag, not a delete.
- `snapshots`: raster of the board up to `upToSeq`, so a late joiner does not download tens of thousands of strokes.

Indexes are created on startup in `app/db.py`: room code unique, room activity, stroke replay `(roomId, seq)`, undo `(roomId, userId, active, seq)`, tool, time, snapshot latest.

Redis:

- `INCR` per room for a monotonically increasing `seq` (ordering when two people draw at once).
- Pub/Sub channel per room. Each process publishes events; others fan them out to their local WebSocket clients. The originator is skipped so you do not echo your own stroke twice.
- Presence: hash + TTL of who is in the room.

Rooms and strokes support create, list, get, patch (title / restyle / move), soft undo + redo, hard delete one stroke, clear room, and cascade delete (strokes + snapshots). See `app/routers/rooms.py`.

Aggregations live in `app/aggregations.py`: contributors, tool_usage, activity timeline, complexity buckets, palette, content bounds, room leaderboard (`$lookup`), dashboard (`$facet`), storage profile. UI and `GET /api/analytics/{key}?room=CODE`.

## Scripts

| Command | What it does |
|---|---|
| `.\scripts\run.ps1` | One uvicorn on 8001 |
| `.\scripts\demo-two-instances.ps1` | Two uvicorns, 8001 + 8002 |
| `python scripts\seed.py --strokes 80000 --rooms 5 --wipe` | Synthetic 50k-100k docs |
| `python scripts\make_snapshot.py --all` | Server-side PNG snapshots |
| `python scripts\verify_crud.py --base http://127.0.0.1:8001` | REST CRUD smoke test |
| `python scripts\benchmark_report.py` | Index timing helper |
| `python scripts\build_report.py` / `build_deck.py` | Word / PPT generators (optional) |

## REST

Prefix is `/api`.

- `POST /rooms` · `GET /rooms` · `GET /rooms/{code}` · `PATCH /rooms/{code}` · `DELETE /rooms/{code}`
- `POST /rooms/{code}/strokes` · `GET /rooms/{code}/strokes`
- `PATCH /strokes/{id}` · `POST /strokes/{id}/move` · `DELETE /strokes/{id}`
- `POST /rooms/{code}/undo` · `redo` · `DELETE .../strokes` (clear) · `POST .../compact`
- `GET /analytics` · `GET /analytics/{key}?room=` · `GET /analytics/{key}/explain`
- `GET /admin/health` · `/indexes` · `/stats` · `/benchmark?room=`
- WebSocket `ws://127.0.0.1:8001/ws/{code}?userId=&userName=`

## If it fails

| Symptom | Fix |
|---|---|
| `docker compose` cannot connect | Start Docker Desktop; wait until it is idle |
| Mongo container unhealthy / port in use | Something else on 27017; stop local Mongo or change the compose port (then change `MONGO_URI`) |
| `pymongo.errors.ServerSelectionTimeoutError` | Containers not up, or replica set not initiated. `docker compose logs mongo-init` then `docker compose restart` |
| `Connection refused` on Redis | `docker compose up -d` and check `wb-redis` |
| `python` not found | Install Python 3.11+ and tick "Add to PATH" |
| Scripts blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Page loads, drawing does not sync | Two tabs on the same room code; Redis must be up; for two ports use the demo script |
| Huge room takes forever to open | Run `make_snapshot.py` after seed |
| `ModuleNotFoundError` | Use `.\.venv\Scripts\python.exe`, not system Python |

Health check once the app is up:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/admin/health
```

## Folder layout

```
whiteboard/
  app/                 FastAPI, Mongo/Redis, CRUD, aggregations, WebSocket hub
  static/              lobby + canvas (vanilla JS, no npm)
  scripts/             run, seed, snapshot, verify, pack zip, report helpers
  docs/                measured numbers from our machine (optional)
  docker-compose.yml   mongo:7 replica set + redis:7
  requirements.txt
  .env.example         copy to .env
  README.md            this file
```

You don't need Node or a cloud account. Atlas is optional later: put a `mongodb+srv://...` URI in `.env` and skip Compose Mongo. Redis still needs to be reachable (`REDIS_URL`).

## Sending a zip

If someone cannot clone, from PowerShell:

```powershell
cd d:\nosql\whiteboard
.\scripts\pack-for-friend.ps1
```

That writes `d:\nosql\whiteboard-handoff.zip` next to the `whiteboard` folder.

Do not zip the whole folder by hand with `.venv` inside. It is hundreds of MB and machine-specific. Leave out `.venv/`, `.env`, `logs/`, `__pycache__/`, and `.demo-pids`. Keep `app/`, `static/`, `scripts/`, `docs/`, `docker-compose.yml`, `requirements.txt`, `.env.example`, and `README.md`. They copy `.env.example` to `.env` and make a new venv on their machine.
