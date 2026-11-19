import os
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory

from seed import FIELDS, GAMES, GENRES, NEW_IN_V2, PLAYABLE, REMOVED

BASE_DIR = Path(__file__).parent
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "games.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ru TEXT NOT NULL DEFAULT '',
    name_en TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT 'family',
    players_min INTEGER NOT NULL DEFAULT 2,
    players_max INTEGER NOT NULL DEFAULT 4,
    time_min INTEGER NOT NULL DEFAULT 30,
    age INTEGER NOT NULL DEFAULT 6,
    playable TEXT,
    description_ru TEXT NOT NULL DEFAULT '',
    description_en TEXT NOT NULL DEFAULT '',
    rules_ru TEXT NOT NULL DEFAULT '',
    rules_en TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0,
    rating INTEGER NOT NULL DEFAULT 0
)
"""

TEXT_FIELDS = ["name_ru", "name_en", "description_ru", "description_en", "rules_ru", "rules_en"]
NUMBER_LIMITS = {"players_min": (1, 99), "players_max": (1, 99), "time_min": (1, 9999), "age": (0, 99)}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=15)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA_VERSION = 3


def init_db():
    db = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("BEGIN IMMEDIATE")
    db.execute(SCHEMA)
    placeholders = ", ".join("?" for _ in FIELDS)
    insert = f"INSERT INTO games ({', '.join(FIELDS)}) VALUES ({placeholders})"
    version = db.execute("PRAGMA user_version").fetchone()[0]
    fresh = db.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0 and version == 0
    if fresh:
        db.executemany(insert, GAMES)
    elif version < 2:
        for name_en, playable in PLAYABLE.items():
            db.execute("UPDATE games SET playable = ? WHERE name_en = ?", (playable, name_en))
        existing = {row[0] for row in db.execute("SELECT name_en FROM games")}
        db.executemany(insert, [game for game in GAMES if game[1] in NEW_IN_V2 and game[1] not in existing])
    if version < 3 and not (version == 0 and fresh):
        db.executemany("DELETE FROM games WHERE name_en = ?", [(name,) for name in REMOVED])
        db.execute("UPDATE games SET playable = NULL WHERE playable IN ('mancala', 'morris', 'hex')")
        for name_en, playable in PLAYABLE.items():
            db.execute("UPDATE games SET playable = ? WHERE name_en = ?", (playable, name_en))
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    db.execute("COMMIT")
    db.close()


def row_to_dict(row):
    game = dict(row)
    game["favorite"] = bool(game["favorite"])
    return game


def validate(data):
    values = {}
    for field in TEXT_FIELDS:
        values[field] = str(data.get(field, "")).strip()
    if not values["name_ru"] and not values["name_en"]:
        return None, "name_required"
    genre = data.get("genre")
    if genre not in GENRES:
        return None, "invalid_genre"
    values["genre"] = genre
    for field, (low, high) in NUMBER_LIMITS.items():
        try:
            number = int(data.get(field))
        except (TypeError, ValueError):
            return None, f"invalid_{field}"
        if not low <= number <= high:
            return None, f"invalid_{field}"
        values[field] = number
    if values["players_min"] > values["players_max"]:
        return None, "invalid_players"
    return values, None


def sort_key(game, sort, lang):
    if sort == "rating":
        return (-game["rating"], game["name_" + lang].lower())
    if sort == "time":
        return (game["time_min"], game["name_" + lang].lower())
    if sort == "players":
        return (game["players_max"], game["name_" + lang].lower())
    return game["name_" + lang].lower()


@app.after_request
def secure(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    if response.mimetype.startswith("font/") or response.mimetype == "application/font-woff2":
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif not request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/health")
def health():
    get_db().execute("SELECT 1").fetchone()
    return jsonify(status="ok")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/games")
def list_games():
    args = request.args
    lang = "en" if args.get("lang") == "en" else "ru"
    query = args.get("q", "").strip().lower()
    genre = args.get("genre", "")
    players = args.get("players", type=int)
    max_time = args.get("max_time", type=int)
    only_favorites = args.get("favorites") == "1"
    only_playable = args.get("playable") == "1"
    sort = args.get("sort", "name")

    games = [row_to_dict(row) for row in get_db().execute("SELECT * FROM games")]
    result = []
    for game in games:
        haystack = " ".join(game[field] for field in TEXT_FIELDS).lower()
        if query and query not in haystack:
            continue
        if genre and game["genre"] != genre:
            continue
        if players and not game["players_min"] <= players <= game["players_max"]:
            continue
        if max_time and game["time_min"] > max_time:
            continue
        if only_favorites and not game["favorite"]:
            continue
        if only_playable and not game["playable"]:
            continue
        result.append(game)

    for game in result:
        game["name_" + lang] = game["name_" + lang] or game["name_ru" if lang == "en" else "name_en"]
    result.sort(key=lambda game: sort_key(game, sort, lang))
    return jsonify(result)


@app.get("/api/games/<int:game_id>")
def get_game(game_id):
    row = get_db().execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if row is None:
        return jsonify(error="not_found"), 404
    return jsonify(row_to_dict(row))


@app.post("/api/games")
def create_game():
    values, error = validate(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    db = get_db()
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    cursor = db.execute(f"INSERT INTO games ({columns}) VALUES ({placeholders})", list(values.values()))
    db.commit()
    row = db.execute("SELECT * FROM games WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.put("/api/games/<int:game_id>")
def update_game(game_id):
    values, error = validate(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    db = get_db()
    assignments = ", ".join(f"{column} = ?" for column in values)
    cursor = db.execute(f"UPDATE games SET {assignments} WHERE id = ?", [*values.values(), game_id])
    db.commit()
    if cursor.rowcount == 0:
        return jsonify(error="not_found"), 404
    row = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    return jsonify(row_to_dict(row))


@app.patch("/api/games/<int:game_id>")
def patch_game(game_id):
    data = request.get_json(silent=True) or {}
    updates = {}
    if "favorite" in data:
        updates["favorite"] = 1 if data["favorite"] else 0
    if "rating" in data:
        try:
            rating = int(data["rating"])
        except (TypeError, ValueError):
            return jsonify(error="invalid_rating"), 400
        if not 0 <= rating <= 5:
            return jsonify(error="invalid_rating"), 400
        updates["rating"] = rating
    if not updates:
        return jsonify(error="nothing_to_update"), 400
    db = get_db()
    assignments = ", ".join(f"{column} = ?" for column in updates)
    cursor = db.execute(f"UPDATE games SET {assignments} WHERE id = ?", [*updates.values(), game_id])
    db.commit()
    if cursor.rowcount == 0:
        return jsonify(error="not_found"), 404
    row = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    return jsonify(row_to_dict(row))


@app.delete("/api/games/<int:game_id>")
def delete_game(game_id):
    db = get_db()
    cursor = db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    db.commit()
    if cursor.rowcount == 0:
        return jsonify(error="not_found"), 404
    return "", 204


init_db()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))