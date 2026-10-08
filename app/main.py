from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import cache, db
from .strength import (
    DEFAULT_FORMULA,
    FORMULAS,
    LiftError,
    compare,
    deload,
    estimates,
    formulas_agree,
    is_personal_best,
    one_rep_max,
    plateau,
    volume,
    warmup_sets,
)

app = FastAPI(title="gym-tracker")

PB_TTL = 7 * 86400


@app.get("/health")
def health():
    out = {"status": "ok", "postgres": False, "redis": False}
    try:
        db.query("SELECT 1")
        out["postgres"] = True
    except Exception as e:
        out["pg_error"] = str(e)
    try:
        cache.client().ping()
        out["redis"] = True
    except Exception as e:
        out["redis_error"] = str(e)
    return out if out["postgres"] and out["redis"] else JSONResponse(out, status_code=503)


def _exercise(name_or_id):
    if str(name_or_id).isdigit():
        row = db.one("SELECT id, name, category FROM exercises WHERE id=%s",
                     (int(name_or_id),))
    else:
        row = db.one("SELECT id, name, category FROM exercises WHERE lower(name)=lower(%s)",
                     (str(name_or_id),))
    if not row:
        raise HTTPException(404, f"no exercise called {name_or_id!r}")
    return row


def _pb(user, ex_id, formula=DEFAULT_FORMULA):
    """Current personal best, from Redis, warmed from Postgres on a miss.

    This is read on every single set logged, which is exactly why it is not a
    SELECT max(...) over the whole lift history each time.
    """
    c = cache.client()
    key = f"pb:{user}:{ex_id}:{formula}"
    hit = c.hgetall(key)
    if hit:
        return {"weight": float(hit["weight"]), "reps": int(hit["reps"]),
                "e1rm": float(hit["e1rm"]), "on": hit.get("on", ""), "source": "redis"}
    rows = db.query("SELECT weight, reps, performed_at FROM lifts"
                    " WHERE user_name=%s AND exercise_id=%s", (user, ex_id))
    best = None
    for r in rows:
        try:
            e = one_rep_max(float(r["weight"]), int(r["reps"]), formula)
        except LiftError:
            continue
        if best is None or e > best["e1rm"]:
            best = {"weight": float(r["weight"]), "reps": int(r["reps"]),
                    "e1rm": e, "on": str(r["performed_at"])[:10]}
    if best:
        c.hset(key, mapping={k: str(v) for k, v in best.items()})
        c.expire(key, PB_TTL)
        return {**best, "source": "postgres"}
    return None


def _store_pb(user, ex_id, formula, pb):
    c = cache.client()
    key = f"pb:{user}:{ex_id}:{formula}"
    c.hset(key, mapping={k: str(v) for k, v in pb.items()})
    c.expire(key, PB_TTL)


@app.get("/exercises")
def exercises():
    rows = db.query("SELECT e.id, e.name, e.category,"
                    " (SELECT count(*) FROM lifts l WHERE l.exercise_id=e.id) AS sets_logged"
                    " FROM exercises e ORDER BY e.category, e.name")
    return {"exercises": rows}


@app.post("/sets", status_code=201)
def log_set(payload: dict = Body(...)):
    user = str(payload.get("user", "")).strip()
    if not user:
        raise HTTPException(400, "user is required")
    ex = _exercise(payload.get("exercise", ""))
    formula = str(payload.get("formula", DEFAULT_FORMULA)).lower()
    if formula not in FORMULAS:
        raise HTTPException(400, f"unknown formula {formula!r} - have {sorted(FORMULAS)}")
    try:
        weight = float(payload.get("weight"))
        reps = int(payload.get("reps"))
        both = estimates(weight, reps)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e) if isinstance(e, LiftError)
                            else "weight and reps are required numbers")

    # Every formula gets its own cache key, so every formula's key has to be
    # judged against this set. Updating only the one the caller asked for
    # leaves the other holding a number that is quietly wrong until it
    # happens to expire - and a stale personal best is worse than no cache.
    # All reads happen before the INSERT, or a cold warm would include the
    # set we are about to compare against itself.
    verdicts = {f: is_personal_best(weight, reps, _pb(user, ex["id"], f), f)
                for f in FORMULAS}
    row = db.one("INSERT INTO lifts (user_name, exercise_id, weight, reps, notes)"
                 " VALUES (%s,%s,%s,%s,%s)"
                 " RETURNING id, user_name, weight, reps, performed_at",
                 (user, ex["id"], weight, reps, str(payload.get("notes", ""))[:200]))
    for f, v in verdicts.items():
        if v["personal_best"]:
            _store_pb(user, ex["id"], f, {"weight": weight, "reps": reps,
                                          "e1rm": v["e1rm"],
                                          "on": str(row["performed_at"])[:10]})
    verdict = verdicts[formula]
    return {"id": row["id"], "user": user, "exercise": ex["name"],
            "weight": float(row["weight"]), "reps": row["reps"],
            "performed_at": row["performed_at"],
            "estimates": both, "verdict": verdict,
            "verdict_by_formula": verdicts}


@app.get("/users/{user}/pbs")
def pbs(user: str, formula: str = DEFAULT_FORMULA):
    if formula not in FORMULAS:
        raise HTTPException(400, f"unknown formula {formula!r}")
    rows = db.query("SELECT DISTINCT e.id, e.name FROM lifts l"
                    " JOIN exercises e ON e.id=l.exercise_id"
                    " WHERE l.user_name=%s ORDER BY e.name", (user,))
    if not rows:
        raise HTTPException(404, "that user has not logged anything")
    out = []
    for r in rows:
        pb = _pb(user, r["id"], formula)
        if pb:
            out.append({"exercise": r["name"], **pb})
    out.sort(key=lambda p: -p["e1rm"])
    return {"user": user, "formula": formula, "personal_bests": out}


@app.get("/users/{user}/exercises/{exercise}/progress")
def progress(user: str, exercise: str, formula: str = DEFAULT_FORMULA):
    if formula not in FORMULAS:
        raise HTTPException(400, f"unknown formula {formula!r}")
    ex = _exercise(exercise)
    rows = db.query("SELECT performed_at::date AS day, weight, reps FROM lifts"
                    " WHERE user_name=%s AND exercise_id=%s"
                    " ORDER BY performed_at", (user, ex["id"]))
    if not rows:
        raise HTTPException(404, "nothing logged for that user and exercise")
    sessions = {}
    for r in rows:
        day = str(r["day"])
        s = sessions.setdefault(day, {"day": day, "sets": []})
        s["sets"].append((float(r["weight"]), int(r["reps"])))
    chart = []
    for day in sorted(sessions):
        sets = sessions[day]["sets"]
        best = max(one_rep_max(w, rp, formula) for w, rp in sets)
        chart.append({"day": day, "sets": len(sets), "best_e1rm": best,
                      "volume": volume(sets),
                      "top_set": max(sets, key=lambda s: one_rep_max(s[0], s[1], formula))})
    stall = plateau([p["best_e1rm"] for p in chart])
    body = {"user": user, "exercise": ex["name"], "formula": formula,
            "sessions": chart, "plateau": stall}
    if stall["stalled"]:
        heaviest = max(float(r["weight"]) for r in rows)
        body["suggestion"] = (
            f"This lift has not moved in {stall['window']} sessions. Drop to "
            f"{deload(heaviest)}kg and build back up, or add a set instead of weight.")
    return body


@app.post("/compare")
def compare_sets(payload: dict = Body(...)):
    try:
        a = {"weight": float(payload["a"]["weight"]), "reps": int(payload["a"]["reps"])}
        b = {"weight": float(payload["b"]["weight"]), "reps": int(payload["b"]["reps"])}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, 'send {"a":{"weight":100,"reps":5},'
                                 '"b":{"weight":110,"reps":3}}')
    formula = str(payload.get("formula", DEFAULT_FORMULA)).lower()
    if formula not in FORMULAS:
        raise HTTPException(400, f"unknown formula {formula!r} - have {sorted(FORMULAS)}")
    try:
        verdict = compare(a, b, formula)
        agree = formulas_agree(a, b)
    except LiftError as e:
        raise HTTPException(400, str(e))
    winner = verdict["a"] if verdict["better"] == "a" else verdict["b"]
    return {**verdict,
            "formulas_agree": agree,
            "note": ("both formulas rank these the same way" if agree else
                     "Epley and Brzycki disagree about these two sets - the answer "
                     "depends entirely on which one you picked"),
            "verdict": ("too close to call" if verdict["better"] == "tie" else
                        f"{winner['weight']:g}kg x {winner['reps']} is the better set")}


@app.get("/users/{user}/exercises/{exercise}/warmup")
def warmup(user: str, exercise: str):
    ex = _exercise(exercise)
    pb = _pb(user, ex["id"])
    if not pb:
        raise HTTPException(404, "no personal best to warm up to yet")
    return {"user": user, "exercise": ex["name"],
            "working_weight": pb["weight"], "from_pb": pb,
            "ladder": warmup_sets(pb["weight"])}
