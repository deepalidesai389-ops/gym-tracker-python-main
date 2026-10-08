"""Pure strength maths. No database, no HTTP.

The app's whole job is answering one question: did that set beat the last
one? You cannot answer it by looking at the weight, because 110kg for 3 and
100kg for 5 are both harder than 100kg for 3. You need a single number that
stands for "how strong was that", and the usual one is the estimated one-rep
max - the weight you could have lifted once.

TWO FORMULAS, ON PURPOSE.

    Epley    e1rm = w * (1 + reps/30)
    Brzycki  e1rm = w * 36 / (37 - reps)

They are both here so they can be compared, because they do not agree and
pretending otherwise is the mistake. They cross at exactly 10 reps. Below
ten Brzycki is the more conservative of the two; above ten it runs away.

On the brief's own question they happen to agree:

    100kg x 5  ->  Epley 116.7   Brzycki 112.5
    110kg x 3  ->  Epley 121.0   Brzycki 116.5     110x3 wins, either way.

Now try this pair, both of them sets a real person could do:

    100kg x 12 ->  Epley 140.0   Brzycki 144.0
    135kg x 2  ->  Epley 144.0   Brzycki 138.9

Epley says the 135x2 was the better set. Brzycki says the 100x12 was. Same
two sets, opposite answers, and nothing about either set is unusual. That is
what the crossover at ten reps does: one formula rewards reps, the other
rewards load. `formulas_agree` exists so you can find pairs like that, and
`compare` takes a formula argument because the app has to pick one and then
never waver - a personal best that depends on which formula ran today is not
a personal best.

Brzycki also has a hole in it: at 37 reps it divides by zero, and above that
it goes negative. Neither formula means anything past about 12 reps anyway.
`MAX_REPS` is where this module stops pretending, and it raises instead.

Worth testing: the four numbers quoted above, to one decimal place; reps=1
returning the weight itself under both formulas; the crossover at reps=10
where they agree exactly; reps=0, reps=-1, weight=0 and a negative weight all
raising; reps above MAX_REPS raising rather than returning nonsense;
`compare` being antisymmetric (compare(a,b) and compare(b,a) must not both
say the same set won); a plateau series that is flat, one that improves by
less than the tolerance, one that improves by more, and one too short to
judge; and `round_to_plates` for a weight that cannot be made at all.
"""

MIN_REPS = 1
MAX_REPS = 12            # past here an e1rm estimate is a guess, not a number
DEFAULT_FORMULA = "epley"

PLATEAU_WINDOW = 3       # sessions with no gain before we say something
PLATEAU_TOLERANCE = 0.5  # kg of estimated 1RM that counts as "no gain"

BAR_KG = 20.0
PLATES = (25.0, 20.0, 15.0, 10.0, 5.0, 2.5, 1.25)
WARMUP_LADDER = ((0.40, 5), (0.60, 4), (0.75, 3), (0.875, 2))


class LiftError(ValueError):
    pass


def _check(weight, reps):
    try:
        w = float(weight)
        r = int(reps)
    except (TypeError, ValueError):
        raise LiftError(f"{weight!r} x {reps!r} is not a set")
    if w <= 0:
        raise LiftError("weight must be greater than zero")
    if r < MIN_REPS:
        raise LiftError("a set is at least one rep")
    if r > MAX_REPS:
        raise LiftError(
            f"{r} reps is past {MAX_REPS} - a one-rep max estimated from that "
            "many reps is fiction, and Brzycki divides by zero at 37")
    return w, r


# --------------------------------------------------------------------------
# the two formulas
# --------------------------------------------------------------------------

def epley(weight, reps):
    w, r = _check(weight, reps)
    return w if r == 1 else w * (1.0 + r / 30.0)


def brzycki(weight, reps):
    w, r = _check(weight, reps)
    return w * 36.0 / (37.0 - r)


FORMULAS = {"epley": epley, "brzycki": brzycki}


def one_rep_max(weight, reps, formula=DEFAULT_FORMULA):
    f = FORMULAS.get(str(formula).lower())
    if f is None:
        raise LiftError(f"unknown formula {formula!r} - have {sorted(FORMULAS)}")
    return round(f(weight, reps), 2)


def estimates(weight, reps):
    """Both numbers side by side, and how far apart they are."""
    e = one_rep_max(weight, reps, "epley")
    b = one_rep_max(weight, reps, "brzycki")
    return {"weight": float(weight), "reps": int(reps),
            "epley": e, "brzycki": b,
            "spread": round(abs(e - b), 2),
            "agree_within_kg": round(abs(e - b), 2) < 1.0}


# --------------------------------------------------------------------------
# which set was better
# --------------------------------------------------------------------------

def compare(a, b, formula=DEFAULT_FORMULA):
    """Is set `a` better than set `b`?

    Each set is (weight, reps) or {"weight":..,"reps":..}. Returns a dict with
    `better` of "a", "b" or "tie", both estimates, and the margin. A tie is
    anything inside a tenth of a kilo - floating point should not decide a
    personal best.
    """
    aw, ar = _unpack(a)
    bw, br = _unpack(b)
    ae = one_rep_max(aw, ar, formula)
    be = one_rep_max(bw, br, formula)
    margin = round(ae - be, 2)
    better = "tie" if abs(margin) < 0.1 else ("a" if margin > 0 else "b")
    return {"formula": str(formula).lower(),
            "a": {"weight": aw, "reps": ar, "e1rm": ae},
            "b": {"weight": bw, "reps": br, "e1rm": be},
            "better": better,
            "margin": abs(margin)}


def _unpack(s):
    if isinstance(s, dict):
        return float(s.get("weight")), int(s.get("reps"))
    w, r = s
    return float(w), int(r)


def formulas_agree(a, b):
    """Do Epley and Brzycki rank these two sets the same way?

    When this is False you have found a pair where the answer depends
    entirely on a choice you made, and that is worth knowing about.
    """
    return compare(a, b, "epley")["better"] == compare(a, b, "brzycki")["better"]


def better_set(a, b, formula=DEFAULT_FORMULA):
    """The stronger of two sets. Ties keep `a`, so an equal set does not
    overwrite a record somebody already has."""
    return a if compare(a, b, formula)["better"] != "b" else b


def is_personal_best(weight, reps, pb, formula=DEFAULT_FORMULA):
    """Did this set beat the stored best?

    Two things can be a record and they are not the same thing: the biggest
    estimated 1RM, and the heaviest bar ever moved for any reps. A 60kg
    triple can be an e1rm record for someone whose best single was 65kg. Both
    are reported, and the app treats e1rm as the one that counts.
    """
    e = one_rep_max(weight, reps, formula)
    w = float(weight)
    if not pb:
        return {"personal_best": True, "heaviest_ever": True, "e1rm": e,
                "previous_e1rm": None, "gain": e,
                "why": "first set recorded for this exercise"}
    prev = float(pb.get("e1rm") or 0)
    prev_w = float(pb.get("weight") or 0)
    gain = round(e - prev, 2)
    return {"personal_best": gain > 0.001,
            "heaviest_ever": w > prev_w,
            "e1rm": e,
            "previous_e1rm": round(prev, 2),
            "gain": gain,
            "why": (f"estimated 1RM up {gain}kg" if gain > 0.001
                    else f"{abs(gain)}kg short of the {prev:.2f}kg best")}


# --------------------------------------------------------------------------
# progress and plateaus
# --------------------------------------------------------------------------

def session_best(sets, formula=DEFAULT_FORMULA):
    """The best estimated 1RM out of one session's working sets."""
    best = 0.0
    for s in sets:
        w, r = _unpack(s)
        best = max(best, one_rep_max(w, r, formula))
    return round(best, 2)


def volume(sets):
    """Total weight moved: sum of weight x reps. A different lens on the same
    session - volume can climb while the top-end estimate sits still, and that
    is exactly what a productive plateau looks like."""
    total = 0.0
    for s in sets:
        w, r = _unpack(s)
        total += w * r
    return round(total, 2)


def plateau(series, window=PLATEAU_WINDOW, tolerance=PLATEAU_TOLERANCE):
    """Has this lift stopped moving?

    `series` is one estimated 1RM per session, oldest first. The rule: take
    the last `window` sessions and the best of everything before them. If the
    recent peak has not beaten the old peak by more than `tolerance`, the
    lift has stalled.

    Using the peak rather than the last value matters - one bad night after a
    personal best is not a plateau, and a rule based on "is today worse than
    yesterday" would scream every other week.
    """
    window = int(window)
    if window < 1:
        raise LiftError("the window must be at least one session")
    values = [float(v) for v in series]
    if len(values) < window + 1:
        return {"stalled": False, "sessions": len(values),
                "reason": f"only {len(values)} sessions - need {window + 1} to judge"}
    recent = values[-window:]
    earlier = values[:-window]
    best_before = max(earlier)
    best_recent = max(recent)
    gain = round(best_recent - best_before, 2)
    stalled = gain <= tolerance
    return {"stalled": stalled,
            "sessions": len(values),
            "window": window,
            "best_before": round(best_before, 2),
            "best_recent": round(best_recent, 2),
            "gain": gain,
            "reason": (f"no gain over the last {window} sessions "
                       f"(best {best_recent:.2f} vs {best_before:.2f})" if stalled
                       else f"up {gain}kg in the last {window} sessions")}


def deload(weight, pct=0.90):
    """What to do about a plateau: back off and build back up."""
    w = float(weight)
    if w <= 0:
        raise LiftError("weight must be greater than zero")
    return round_to_plates(w * float(pct))["weight"]


# --------------------------------------------------------------------------
# loading the bar
# --------------------------------------------------------------------------

def round_to_plates(target, bar=BAR_KG, plates=PLATES):
    """The closest loadable weight at or below the target, and the plates.

    Not every number can be made. Asking for 83kg on a 20kg bar gets you
    82.5kg, and anything under the bar gets you the bar.
    """
    t = float(target)
    if t <= bar:
        return {"weight": float(bar), "per_side": [], "exact": abs(t - bar) < 1e-9}
    per_side_kg = (t - bar) / 2.0
    chosen, left = [], per_side_kg
    for p in sorted(plates, reverse=True):
        while left >= p - 1e-9:
            chosen.append(p)
            left -= p
    total = round(bar + 2 * sum(chosen), 2)
    return {"weight": total, "per_side": chosen, "exact": abs(total - t) < 1e-9}


def warmup_sets(working_weight, bar=BAR_KG, ladder=WARMUP_LADDER):
    """A warm-up ladder up to a working weight, rounded to real plates."""
    w = float(working_weight)
    if w <= 0:
        raise LiftError("weight must be greater than zero")
    out = [{"weight": float(bar), "reps": 8, "note": "empty bar"}]
    for pct, reps in ladder:
        loaded = round_to_plates(w * pct, bar=bar)
        if loaded["weight"] > out[-1]["weight"]:
            out.append({"weight": loaded["weight"], "reps": reps,
                        "note": f"{int(pct * 100)}%"})
    out.append({"weight": round_to_plates(w, bar=bar)["weight"], "reps": None,
                "note": "working sets"})
    return out
