import hashlib
import hmac
import secrets
import sqlite3

DB_FILE = "minichat.db"
DEFAULT_TITLE = "New chat"


def get_connection():
    return sqlite3.connect(DB_FILE)


def init_db():
    """Create the tables if they don't exist yet (and upgrade old databases)."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash BLOB NOT NULL,
                salt          BLOB NOT NULL,
                display_name  TEXT,
                email         TEXT,
                bio           TEXT,
                avatar        BLOB
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                title      TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                conversation_id INTEGER,
                role            TEXT NOT NULL,   -- 'user' or 'assistant'
                content         TEXT NOT NULL,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        # ---- upgrade: profile columns for databases made earlier ----
        user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        for column, kind in (("display_name", "TEXT"), ("email", "TEXT"),
                             ("bio", "TEXT"), ("avatar", "BLOB")):
            if column not in user_columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} {kind}")

        # ---- upgrade: databases made before conversations existed ----
        columns = [row[1] for row in conn.execute("PRAGMA table_info(messages)")]
        if "conversation_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN conversation_id INTEGER")

        owners = conn.execute(
            "SELECT DISTINCT user_id FROM messages WHERE conversation_id IS NULL"
        ).fetchall()
        for (user_id,) in owners:
            cursor = conn.execute(
                "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
                (user_id, "Previous chat"),
            )
            conn.execute(
                "UPDATE messages SET conversation_id = ? "
                "WHERE user_id = ? AND conversation_id IS NULL",
                (cursor.lastrowid, user_id),
            )


# ---------------- app settings (remembers dark/light mode) ----------------
def get_setting(key, default=None):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key, value):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )


# ---------------- users ----------------
def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


def register_user(username, password):
    """Returns (True, message) or (False, message)."""
    salt = secrets.token_bytes(16)
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, _hash_password(password, salt), salt),
            )
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "That username is already taken."


def login_user(username, password):
    """Returns the user id if the login is correct, otherwise None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash, salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row and hmac.compare_digest(row[1], _hash_password(password, row[2])):
        return row[0]
    return None


# ---------------- profile ----------------
def get_profile(user_id):
    """Returns a dict: username, display_name, email, bio, avatar (PNG bytes or None)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, display_name, email, bio, avatar FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return {"username": "", "display_name": "", "email": "", "bio": "", "avatar": None}
    return {
        "username": row[0],
        "display_name": row[1] or "",
        "email": row[2] or "",
        "bio": row[3] or "",
        "avatar": row[4],
    }


def update_profile(user_id, display_name, email, bio):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET display_name = ?, email = ?, bio = ? WHERE id = ?",
            (display_name, email, bio, user_id),
        )


def set_avatar(user_id, image_bytes):
    """Saves the profile picture (PNG bytes). Pass None to remove it."""
    with get_connection() as conn:
        conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (image_bytes, user_id))


# ---------------- conversations ----------------
def create_conversation(user_id, title=DEFAULT_TITLE):
    """Makes a new empty conversation and returns its id."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
            (user_id, title),
        )
        return cursor.lastrowid


def get_conversations(user_id):
    """Returns a list of (id, title), most recently used first."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, title FROM conversations WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()


def rename_conversation(conversation_id, title):
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conversation_id),
        )


def delete_conversation(conversation_id):
    """Deletes the conversation and all of its messages."""
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


# ---------------- chat messages ----------------
def add_message(user_id, conversation_id, role, content):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, conversation_id, role, content) "
            "VALUES (?, ?, ?, ?)",
            (user_id, conversation_id, role, content),
        )
        # Moves this conversation to the top of the sidebar
        conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )


def get_messages(conversation_id, limit=None):
    """Returns a list of (role, content), oldest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return rows[-limit:] if limit else rows