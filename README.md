# Real-Time Collaborative Whiteboard

Course project (BCSE406L, NoSQL Database). A shared HTML5 canvas backed by **MongoDB** (rooms, append-only strokes, snapshots) and **Redis** (sequence numbers, presence, Pub/Sub so two Python processes stay in sync).

This README is the full local-setup guide. Send this folder (or the zip from `scripts\pack-for-friend.ps1`) and start here.

---

## 1. What to send (you, the original machine)

Do **not** zip the whole `whiteboard` folder as-is. `.venv` is hundreds of MB of machine-specific Python packages. Docker volumes and `.env` stay on your PC.

From PowerShell:

```powershell
cd d:\nosql\whiteboard
.\scripts\pack-for-friend.ps1
```

That writes `d:\nosql\whiteboard-handoff.zip` (next to the `whiteboard` folder). Send that zip by Drive, WhatsApp, USB, whatever.

If you pack by hand, include:

| Include | Skip |
|---|---|
| `app/`, `static/`, `scripts/`, `docs/` | `.venv/` |
| `docker-compose.yml`, `requirements.txt` | `.env` (local only) |
| `.env.example`, `README.md` | `logs/`, `__pycache__/`, `.demo-pids` |

Your friend recreates `.env` from `.env.example` and installs packages into a **new** venv on their machine.

---

## 2. What your friend needs

| Tool | Why |
|---|---|
| **Windows 10/11**, macOS, or Linux | Code is portable; the helper scripts are PowerShell |
| **Python 3.11+** | App uses modern type syntax (`dict \| None`) |
| **Docker Desktop** | Runs MongoDB 7 (replica set `rs0`) and Redis 7 |
| Free ports **27017**, **6379**, **8001** (and **8002** for the two-server demo) | Compose binds Mongo/Redis; uvicorn binds 8001 |

Install Docker Desktop and make sure it is **running** (whale icon in the tray) before `docker compose`. First pull of `mongo:7` and `redis:7-alpine` needs internet.

If something already uses 27017 (a local MongoDB install), stop it or the container will fail to bind.

---

## 3. Setup (first time)

Unzip so you have a folder named `whiteboard` (or `whiteboard-handoff`) with `docker-compose.yml` at the top.

**Windows (PowerShell):**

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

You want `wb-mongo` and `wb-redis` **Up (healthy)**. The one-shot `mongo-init` container initiates replica set `rs0` and then exits. That is normal.

Seed a large dataset (needed for analytics and index demo; takes a few minutes):

```powershell
.\.venv\Scripts\python.exe scripts\seed.py --strokes 80000 --rooms 5 --wipe
```

Prints the **largest room code** at the end (random 6-letter code). Write it down.

Optional: bake a canvas snapshot so joining that huge room is fast:

```powershell
.\.venv\Scripts\python.exe scripts\make_snapshot.py --all
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
python scripts/seed.py --strokes 80000 --rooms 5 --wipe
python scripts/make_snapshot.py --all
```

`.env` for local Docker is already correct in `.env.example`:

```
MONGO_URI=mongodb://localhost:27017/?directConnection=true
MONGO_DB=whiteboard
REDIS_URL=redis://localhost:6379/0
SNAPSHOT_INTERVAL=500
```

`directConnection=true` is required because Compose runs a **single-node replica set** advertised as `localhost:27017`.

---

## 4. Run the app

**One server (normal use):**

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

Open **http://127.0.0.1:8001**

**Two servers (Redis crossing process boundaries):**

```powershell
.\scripts\demo-two-instances.ps1
```

Open the **same room code** in two browser windows:

- http://127.0.0.1:8001  → badge `wb-1`
- http://127.0.0.1:8002  → badge `wb-2`

Draw in one window; ink and cursors appear in the other. That path is Redis Pub/Sub, not a shared Python process.

Stop both:

```powershell
.\scripts\demo-two-instances.ps1 -Stop
```

**Stop everything (app + Docker):**

```powershell
.\scripts\demo-two-instances.ps1 -Stop
docker compose down
```

`docker compose down` keeps the Mongo volume. Data is still there next `up`. To wipe the database volume as well: `docker compose down -v`.

---

## 5. How to use the UI

1. Enter a display name on the lobby.
2. **Create new board** or type a room code and join. Seeded rooms show in the recent list; the large one is best for Analytics / Indexes.
3. Draw with pen, eraser, rectangle, ellipse, line. Undo / redo is per user.
4. Share the room code (click the chip) so another browser can join.
5. **Analytics** — runs MongoDB aggregation pipelines against the current room.
6. **Indexes** — times the same queries with indexes vs collection scan (`explain` COLLSCAN vs IXSCAN).
7. REST explorer: **http://127.0.0.1:8001/docs** (FastAPI Swagger).

---

## 6. How the system is put together

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

**MongoDB collections**

- `rooms` — `code` (unique 6-char), title, participants, `strokeCount`, `lastActivityAt`, archive flag.
- `strokes` — one document per stroke: `roomId`, `seq`, `userId`, `tool`, `style`, `points[]`, `bbox`, `active` (false after undo), `createdAt`. Append-only; undo is a flag, not a delete.
- `snapshots` — raster of the board up to `upToSeq`, so a late joiner does not download tens of thousands of strokes.

**Indexes** (created on startup in `app/db.py`): room code unique, room activity, stroke replay `(roomId, seq)`, undo `(roomId, userId, active, seq)`, tool, time, snapshot latest.

**Redis**

- `INCR` per room for monotonically increasing `seq` (ordering when two people draw at once).
- Pub/Sub channel per room: each process publishes events; others fan them out to their local WebSocket clients. The originator is skipped so you do not echo your own stroke twice.
- Presence: hash + TTL of who is in the room.

**CRUD (review requirement)** — rooms and strokes: create, list, get, patch (title / restyle / move), soft undo + redo, hard delete one stroke, clear room, cascade delete room (strokes + snapshots). See `app/routers/rooms.py`.

**Aggregations** — `app/aggregations.py`: contributors, tool_usage, activity timeline, complexity buckets, palette, content bounds, room leaderboard (`$lookup`), dashboard (`$facet`), storage profile. UI and `GET /api/analytics/{key}?room=CODE`.

---

## 7. Useful scripts

| Command | What it does |
|---|---|
| `.\scripts\run.ps1` | One uvicorn on 8001 |
| `.\scripts\demo-two-instances.ps1` | Two uvicorns, 8001 + 8002 |
| `python scripts\seed.py --strokes 80000 --rooms 5 --wipe` | Synthetic 50k–100k docs |
| `python scripts\make_snapshot.py --all` | Server-side PNG snapshots |
| `python scripts\verify_crud.py --base http://127.0.0.1:8001` | REST CRUD smoke test |
| `python scripts\benchmark_report.py` | Index timing helper |
| `python scripts\build_report.py` / `build_deck.py` | Word / PPT generators (optional) |

---

## 8. REST map (short)

Prefix is `/api`.

- `POST /rooms` · `GET /rooms` · `GET /rooms/{code}` · `PATCH /rooms/{code}` · `DELETE /rooms/{code}`
- `POST /rooms/{code}/strokes` · `GET /rooms/{code}/strokes`
- `PATCH /strokes/{id}` · `POST /strokes/{id}/move` · `DELETE /strokes/{id}`
- `POST /rooms/{code}/undo` · `redo` · `DELETE .../strokes` (clear) · `POST .../compact`
- `GET /analytics` · `GET /analytics/{key}?room=` · `GET /analytics/{key}/explain`
- `GET /admin/health` · `/indexes` · `/stats` · `/benchmark?room=`
- WebSocket `ws://127.0.0.1:8001/ws/{code}?userId=&userName=`

---

## 9. If it fails

| Symptom | Fix |
|---|---|
| `docker compose` cannot connect | Start Docker Desktop; wait until it is idle |
| Mongo container unhealthy / port in use | Something else on 27017; stop local Mongo or change the compose port (then change `MONGO_URI`) |
| `pymongo.errors.ServerSelectionTimeoutError` | Containers not up, or replica set not initiated — `docker compose logs mongo-init` then `docker compose restart` |
| `Connection refused` on Redis | `docker compose up -d` and check `wb-redis` |
| `python` not found | Install Python 3.11+ and tick “Add to PATH” |
| Scripts blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Page loads, drawing does not sync | Two tabs on **same** room code; Redis must be up; for two ports use the demo script |
| Huge room takes forever to open | Run `make_snapshot.py` after seed |
| `ModuleNotFoundError` | Use `.\.venv\Scripts\python.exe`, not system Python |

Health check once the app is up:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/admin/health
```

---

## 10. Layout of this folder

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

No Node.js, no cloud account. Atlas is optional later: put a `mongodb+srv://...` URI in `.env` and skip Compose Mongo. Redis still needs to be reachable (`REDIS_URL`).
