import pytest

from app.strength import (
    LiftError,
    epley,
    brzycki,
    one_rep_max,
    estimates,
    compare,
    formulas_agree,
    better_set,
    is_personal_best,
    session_best,
    volume,
    plateau,
    deload,
    round_to_plates,
    warmup_sets,
)


def test_formulas():
    assert epley(100, 5) == pytest.approx(116.67, abs=0.01)
    assert brzycki(100, 5) == pytest.approx(112.5)
    assert epley(100, 1) == 100
    assert brzycki(100, 1) == 100
    assert epley(100, 10) == pytest.approx(brzycki(100, 10))


def test_opposite_formula_winners():
    a = {"weight": 100, "reps": 12}
    b = {"weight": 135, "reps": 2}

    assert compare(a, b, "epley")["better"] == "b"
    assert compare(a, b, "brzycki")["better"] == "a"


def test_12_reps_accepted():
    assert epley(100, 12) == 140.0


def test_13_reps_refused():
    with pytest.raises(ValueError):
        epley(100, 13)


def test_invalid_values():
    for weight, reps in [
        (0, 5),
        (-10, 5),
        (100, 0),
        (100, -1),
    ]:
        with pytest.raises(LiftError):
            epley(weight, reps)


def test_one_rep_max():
    assert one_rep_max(100, 5, "epley") == 116.67
    assert one_rep_max(100, 5, "brzycki") == 112.5

    with pytest.raises(LiftError):
        one_rep_max(100, 5, "wrong")


def test_estimates():
    result = estimates(100, 5)

    assert result["weight"] == 100.0
    assert result["reps"] == 5
    assert result["epley"] == pytest.approx(116.67, abs=0.01)
    assert result["brzycki"] == 112.5
    assert result["spread"] > 0


def test_compare():
    a = {"weight": 100, "reps": 5}
    b = {"weight": 110, "reps": 3}

    result = compare(a, b)
    reverse = compare(b, a)

    assert result["better"] == "b"
    assert reverse["better"] == "a"


def test_compare_never_says_both_win():
    a = {"weight": 100, "reps": 5}
    b = {"weight": 110, "reps": 3}

    ab = compare(a, b)
    ba = compare(b, a)

    assert not (
        ab["better"] == "a" and ba["better"] == "a"
    )


def test_formulas_agree():
    a = {"weight": 100, "reps": 5}
    b = {"weight": 110, "reps": 3}

    assert formulas_agree(a, b) is True


def test_better_set():
    a = {"weight": 100, "reps": 5}
    b = {"weight": 110, "reps": 3}

    assert better_set(a, b) == b


def test_personal_best():
    assert is_personal_best(100, 5, None)["personal_best"] is True

    previous = {"e1rm": 100}
    result = is_personal_best(110, 3, previous)

    assert result["personal_best"] is True


def test_session_best():
    sets = [
        {"weight": 100, "reps": 5},
        {"weight": 110, "reps": 3},
    ]

    assert session_best(sets) == 121.0


def test_volume():
    sets = [
        {"weight": 100, "reps": 5},
        {"weight": 110, "reps": 3},
    ]

    assert volume(sets) == 830.0


def test_plateau():
    assert plateau([100, 101])["stalled"] is False

    result = plateau([100, 100.2, 100.3])
    assert result["stalled"] is False


def test_deload():
    assert deload(100) == 90.0


def test_round_to_plates():
    result = round_to_plates(83)

    assert result["weight"] == 82.5
    assert result["exact"] is False


def test_warmup_sets():
    result = warmup_sets(100)

    assert len(result) > 0
    assert result[-1]["weight"] == 100.0
