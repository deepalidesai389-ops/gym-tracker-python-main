CREATE TABLE IF NOT EXISTS exercises (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general');
CREATE UNIQUE INDEX IF NOT EXISTS exercises_name ON exercises (lower(name));

CREATE TABLE IF NOT EXISTS lifts (
    id SERIAL PRIMARY KEY,
    user_name TEXT NOT NULL,
    exercise_id INT NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    weight NUMERIC(6,2) NOT NULL CHECK (weight > 0),
    reps INT NOT NULL CHECK (reps >= 1),
    notes TEXT NOT NULL DEFAULT '',
    performed_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE INDEX IF NOT EXISTS lifts_user_ex ON lifts (user_name, exercise_id, performed_at);
