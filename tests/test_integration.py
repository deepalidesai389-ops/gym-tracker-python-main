import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import db, cache


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["postgres"] is True
    assert data["redis"] is True


def test_exercises():
    response = client.get("/exercises")

    assert response.status_code == 200
    data = response.json()

    assert "exercises" in data
    assert len(data["exercises"]) > 0


def test_compare():
    response = client.post(
        "/compare",
        json={
            "a": {"weight": 100, "reps": 5},
            "b": {"weight": 110, "reps": 3},
            "formula": "epley",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["better"] == "b"
    assert "verdict" in data
    assert "formulas_agree" in data


def test_compare_invalid_formula():
    response = client.post(
        "/compare",
        json={
            "a": {"weight": 100, "reps": 5},
            "b": {"weight": 110, "reps": 3},
            "formula": "wrong",
        },
    )

    assert response.status_code == 400


def test_log_set():
    response = client.post(
        "/sets",
        json={
            "user": "testuser",
            "exercise": "Bench Press",
            "weight": 100,
            "reps": 5,
            "formula": "epley",
            "notes": "integration test",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user"] == "testuser"
    assert data["weight"] == 100
    assert data["reps"] == 5
    assert "estimates" in data
    assert "verdict" in data
    assert "verdict_by_formula" in data


def test_personal_bests():
    response = client.get("/users/testuser/pbs")

    assert response.status_code == 200

    data = response.json()

    assert data["user"] == "testuser"
    assert len(data["personal_bests"]) > 0


def test_progress():
    response = client.get(
        "/users/testuser/exercises/Bench Press/progress"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["user"] == "testuser"
    assert data["exercise"] == "Bench Press"
    assert len(data["sessions"]) > 0
    assert "plateau" in data


def test_warmup():
    response = client.get(
        "/users/testuser/exercises/Bench Press/warmup"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["user"] == "testuser"
    assert data["exercise"] == "Bench Press"
    assert "ladder" in data


def test_missing_user():
    response = client.post(
        "/sets",
        json={
            "exercise": "Bench Press",
            "weight": 100,
            "reps": 5,
        },
    )

    assert response.status_code == 400


def test_unknown_exercise():
    response = client.post(
        "/sets",
        json={
            "user": "testuser2",
            "exercise": "Does Not Exist",
            "weight": 100,
            "reps": 5,
        },
    )

    assert response.status_code == 404


def test_invalid_set():
    response = client.post(
        "/sets",
        json={
            "user": "testuser2",
            "exercise": "Bench Press",
            "weight": 100,
            "reps": 13,
        },
    )

    assert response.status_code == 400


def test_unknown_formula():
    response = client.post(
        "/sets",
        json={
            "user": "testuser2",
            "exercise": "Bench Press",
            "weight": 100,
            "reps": 5,
            "formula": "wrong",
        },
    )

    assert response.status_code == 400


def test_missing_progress():
    response = client.get(
        "/users/user_that_does_not_exist/exercises/Bench Press/progress"
    )

    assert response.status_code == 404


def test_missing_warmup():
    response = client.get(
        "/users/user_that_does_not_exist/exercises/Bench Press/warmup"
    )

    assert response.status_code == 404
