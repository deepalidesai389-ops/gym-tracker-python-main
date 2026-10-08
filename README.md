# Gym Progress Tracker

**Language:** Python (FastAPI) &nbsp;|&nbsp; **Needs:** Postgres + Redis

This is a **starter**. The application already works. Your job is everything
that gets it building, tested and running in CI.

---

## You do not need Python installed

You will build this into a container, and the container brings its own
Python 3.12. You are not being asked to extend the app — you are being asked
to ship it.

---

## 1. What this app needs

| | |
|---|---|
| **Runtime** | Python 3.12 |
| **Install dependencies** | `pip install -r requirements.txt` |
| **Start the app** | `uvicorn app.main:app --host 0.0.0.0 --port 8080` |
| **Listens on** | port 8080, bound to `0.0.0.0` |
| **Environment variables** | `DATABASE_URL`, `REDIS_URL` |
| **Needs running first** | Postgres, Redis, and the migrations applied |

### What it does

Log every set: exercise, weight, reps. The app tells you straight away whether that was a personal best, keeps a per-exercise record, charts your estimated one-rep max session by session, and shouts when a lift has not moved in weeks. It carries two different one-rep-max formulas so you can see them disagree.

### Endpoints

```
GET  /health
GET  /exercises
POST /sets                                      {"user":"asha","exercise":"Bench Press","weight":65,"reps":4}
GET  /users/{user}/pbs                          ?formula=epley|brzycki
GET  /users/{user}/exercises/{exercise}/progress session chart + plateau warning
GET  /users/{user}/exercises/{exercise}/warmup   a plate-rounded warm-up ladder
POST /compare                                   {"a":{"weight":100,"reps":5},"b":{"weight":110,"reps":3}}
```

`/health` reports Postgres and Redis **separately**. If it says
`postgres: false` the app started fine and your compose wiring is wrong —
do not go looking in the application code.

### Migrations

`migrations/` holds `.sql` files applied **in filename order** before the app
starts. They create the tables and insert sample data. A container running
`psql` over them in order is enough; you do not need a migration tool.

---

## 2. What you must write

| File | What it has to do |
|---|---|
| `Dockerfile` | Install dependencies **before** copying source, pin the base image, do not run as root. |
| `docker-compose.yml` | App + Postgres + Redis + a migration step, one `docker compose up`. |
| `.circleci/config.yml` | lint → unit tests → integration tests → secret scan → image build |
| Unit tests | For `app/strength.py`. No database, no network. |
| Integration tests | Against a real Postgres and Redis as CircleCI service containers. |

Then push your image to **your own Docker Hub account**, tagged `:1.0`.

### When it works

```bash
docker compose up --build
curl localhost:8080/health
```

```json
{"status":"ok","postgres":true,"redis":true}
```

---

## Where the marks are

`app/strength.py` is **pure logic** — plain functions over plain data, no
database and no HTTP. Start your tests there. Use pytest:
`pytest --cov=app --cov-report=term-missing`. Minimum 70%.

Formula choice: The app uses Epley as the default formula for one-rep-max estimation and comparison because it provides a simple and consistent estimate across the supported 1–12 rep range. Brzycki is also supported as an alternative formula when explicitly selected. The selected formula is included in the Redis personal-best key so results from different formulas remain separate.
The module docstring hands you a pair of sets where Epley and Brzycki give opposite answers. Write that test first, then decide which formula the app commits to and why. Then check that `compare` never says both sets won, and that a 12-rep set is accepted while a 13-rep set is refused.

## Why Redis is here

The personal best for every user and exercise lives in a Redis hash, and it is read on every single set logged - that is the hot path. The alternative is a `max()` over the user's entire lift history on every POST, which gets slower every week they train. The cache is warmed from Postgres on a miss, so wiping Redis costs one slow request and nothing else. Note the formula is part of the key: a best computed with Epley is not a best computed with Brzycki.

## The hard part

Is 100kg for 5 reps better than 110kg for 3? Your formula has to decide, and be consistent about it.

Write your answer in your README. It is worth more marks than the feature.

---

## Getting unstuck

| Symptom | Almost always |
|---|---|
| `/health` says `postgres: false` | Wrong hostname. In compose the host is the **service name**, not `localhost`. |
| Page will not load, logs fine | No `ports:` mapping, or bound to `127.0.0.1` not `0.0.0.0`. |
| `relation "..." does not exist` | Migrations did not run, or the app started before they finished. |
| Build takes minutes each time | `COPY . .` is above your dependency install. |
| CI cannot reach the database | In CircleCI service containers the host **is** `localhost` — opposite of compose. |
