"""SQLite catalog index for the problem set (issue #39).

The filesystem remains the source of truth: each ``problems/<id>/problem.json``
is canonical. SQLite is used purely as a derived, rebuildable *index* so that
catalog listing, filtering, and prerequisite lookups scale without scanning and
parsing every JSON file on each invocation.

Design notes:
- Zero dependencies: uses the stdlib ``sqlite3`` module only.
- The database lives under ``~/.local/share/tutor/catalog.db`` alongside the
  existing progress/config state.
- Staleness detection uses per-problem content hashes, so re-indexing only
  reparses changed problems.
- If the database is missing or corrupt it is simply rebuilt from disk; no
  user data can be lost because nothing authoritative is stored here.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from tutor.state import STATE_DIR

DB_PATH = STATE_DIR / "catalog.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS problems (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    track         TEXT,
    category      TEXT,
    difficulty    TEXT,
    dir           TEXT NOT NULL,
    languages     TEXT NOT NULL DEFAULT '[]',
    depends_on    TEXT NOT NULL DEFAULT '[]',
    tags          TEXT NOT NULL DEFAULT '[]',
    colspec       TEXT NOT NULL DEFAULT '[]',
    spec          TEXT NOT NULL DEFAULT '',
    content_hash  TEXT NOT NULL,
    indexed_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    problem_id  TEXT NOT NULL,
    dep_id      TEXT NOT NULL,
    PRIMARY KEY (problem_id, dep_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_problems_difficulty ON problems(difficulty);
CREATE INDEX IF NOT EXISTS idx_problems_category   ON problems(category);
CREATE INDEX IF NOT EXISTS idx_deps_dep            ON dependencies(dep_id);
"""


def _hash_problem(meta_file: Path) -> str:
    return hashlib.sha256(meta_file.read_bytes()).hexdigest()[:16]


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    return conn


def _row_to_problem(row: sqlite3.Row) -> Dict[str, Any]:
    p = dict(row)
    for key in ("languages", "depends_on", "tags", "colspec"):
        try:
            p[key] = json.loads(p.get(key) or "[]")
        except (TypeError, json.JSONDecodeError):
            p[key] = []
    return p


class CatalogIndex:
    """Incremental SQLite index over on-disk ``problem.json`` files."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self._db_path)
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def sync(self, search_paths: List[Path]) -> int:
        """Reconcile the index with the given problem directories.

        Returns the number of problems (re)inserted. Problems whose directory
        disappeared are pruned. Never raises on individual bad problem.json
        files — those are skipped, matching the previous scanner behavior.
        """
        from datetime import datetime, timezone

        live_ids: Dict[str, Path] = {}  # id -> meta file
        for base in search_paths:
            base = Path(base)
            if not base.exists():
                continue
            for prob_dir in sorted(base.iterdir()):
                meta_file = prob_dir / "problem.json"
                if not prob_dir.is_dir() or not meta_file.exists():
                    continue
                live_ids.setdefault(prob_dir.name, meta_file)

        existing = {
            r["id"]: r["content_hash"]
            for r in self.conn.execute("SELECT id, content_hash FROM problems")
        }

        changed = 0
        for pid, meta_file in live_ids.items():
            try:
                digest = _hash_problem(meta_file)
            except OSError:
                continue
            if existing.get(pid) == digest:
                continue
            try:
                meta = json.loads(meta_file.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            meta_id = meta.get("id", pid)
            row = {
                "id": meta_id,
                "title": meta.get("title", meta_id),
                "track": meta.get("track", meta.get("category", "Systems")),
                "category": meta.get("category", ""),
                "difficulty": meta.get("difficulty", ""),
                "dir": str(meta_file.parent),
                "languages": json.dumps(meta.get("languages", [])),
                "depends_on": json.dumps(meta.get("depends_on", [])),
                "tags": json.dumps(meta.get("tags", [])),
                "colspec": json.dumps(meta.get("colspec", [])),
                "spec": meta.get("spec", ""),
                "content_hash": digest,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.conn.execute(
                """
                INSERT INTO problems (id, title, track, category, difficulty, dir,
                                      languages, depends_on, tags, colspec, spec,
                                      content_hash, indexed_at)
                VALUES (:id, :title, :track, :category, :difficulty, :dir,
                        :languages, :depends_on, :tags, :colspec, :spec,
                        :content_hash, :indexed_at)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, track=excluded.track,
                    category=excluded.category, difficulty=excluded.difficulty,
                    dir=excluded.dir, languages=excluded.languages,
                    depends_on=excluded.depends_on, tags=excluded.tags,
                    colspec=excluded.colspec, spec=excluded.spec,
                    content_hash=excluded.content_hash,
                    indexed_at=excluded.indexed_at
                """,
                row,
            )
            self.conn.execute("DELETE FROM dependencies WHERE problem_id = ?", (meta_id,))
            for dep in meta.get("depends_on", []):
                self.conn.execute(
                    "INSERT OR IGNORE INTO dependencies (problem_id, dep_id) VALUES (?, ?)",
                    (meta_id, dep),
                )
            changed += 1

        stale = [pid for pid in existing if pid not in live_ids]
        for pid in stale:
            self.conn.execute("DELETE FROM problems WHERE id = ?", (pid,))
            self.conn.execute("DELETE FROM dependencies WHERE problem_id = ?", (pid,))
            changed += 1

        self.conn.commit()
        return changed

    def all_problems(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM problems ORDER BY id").fetchall()
        return [_row_to_problem(r) for r in rows]

    def get(self, problem_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM problems WHERE id = ?", (problem_id,)
        ).fetchone()
        return _row_to_problem(row) if row else None

    def dependents_of(self, problem_id: str) -> List[str]:
        rows = self.conn.execute(
            "SELECT problem_id FROM dependencies WHERE dep_id = ?", (problem_id,)
        ).fetchall()
        return [r["problem_id"] for r in rows]

    def counts_by(self, column: str) -> Dict[str, int]:
        if column not in ("difficulty", "category", "track"):
            raise ValueError(f"unsupported grouping column: {column}")
        rows = self.conn.execute(
            f"SELECT {column} AS k, COUNT(*) AS n FROM problems GROUP BY {column}"
        ).fetchall()
        return {r["k"]: r["n"] for r in rows}
