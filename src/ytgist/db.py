import sqlite3
from ytgist.transcript import cache_dir

def db_path():
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "ytgist.db"

def get_conn():
    conn = sqlite3.connect(db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL REFERENCES videos(video_id),
            model TEXT NOT NULL,
            prompt TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_video ON summaries(video_id)")
    return conn

def ensure_video(video_id, url, title=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO videos (video_id, url, title) VALUES (?, ?, ?)
        ON CONFLICT(video_id) DO NOTHING
    """, (video_id, url, title))
    conn.commit()
    conn.close()

def add_summary(video_id, model, prompt, summary):
    conn = get_conn()
    conn.execute("""
        INSERT INTO summaries (video_id, model, prompt, summary)
        VALUES (?, ?, ?, ?)
    """, (video_id, model, prompt, summary))
    conn.commit()
    conn.close()

def recent_videos(limit=10):
    """Last N videos with their summary count, most recently summarized first."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT v.video_id, v.url, v.title, MAX(s.created_at) AS last_run,
               COUNT(s.id) AS summary_count
        FROM videos v JOIN summaries s ON s.video_id = v.video_id
        GROUP BY v.video_id
        ORDER BY last_run DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows

def summaries_for(video_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, model, prompt, summary, created_at
        FROM summaries WHERE video_id=? ORDER BY created_at DESC
    """, (video_id,)).fetchall()
    conn.close()
    return rows