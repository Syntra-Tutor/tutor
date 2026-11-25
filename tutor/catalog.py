import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from tutor.state import is_solved, get_progress

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PROBLEMS = REPO_ROOT / "problems"
USER_PROBLEMS = Path.home() / ".local" / "share" / "tutor" / "problems"

DEFAULT_COLSPEC = [
    {"hdr": "Score", "asc": False},
    {"hdr": "Cycles/Op", "asc": True},
    {"hdr": "Bytes", "asc": True},
]


def _normalize_meta(meta: Dict[str, Any], prob_dir: Path) -> Dict[str, Any]:
    meta["dir"] = str(prob_dir)
    meta.setdefault("depends_on", [])
    if not meta.get("colspec"):
        meta["colspec"] = DEFAULT_COLSPEC
    meta.setdefault("track", meta.get("category", "Systems"))
    return meta


class ProblemCatalog:
    """Discovers, indexes, and resolves prerequisite DAGs for available problem sets.

    Uses an incremental SQLite index (``tutor.db.CatalogIndex``, issue #39) to
    avoid rescanning/parsing every ``problem.json`` on each invocation. The
    on-disk JSON files remain the source of truth; if the database layer is
    unavailable we transparently fall back to a direct filesystem scan.
    """

    def __init__(self):
        self.search_paths = [BUILTIN_PROBLEMS, USER_PROBLEMS]

    def _scan_filesystem(self) -> List[Dict[str, Any]]:
        problems = []
        seen_ids = set()

        for base_path in self.search_paths:
            if not base_path.exists():
                continue
            for prob_dir in sorted(base_path.iterdir()):
                if not prob_dir.is_dir():
                    continue
                meta_file = prob_dir / "problem.json"
                if not meta_file.exists():
                    continue
                try:
                    with open(meta_file, "r") as f:
                        meta = json.load(f)
                    pid = meta.get("id", prob_dir.name)
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    _normalize_meta(meta, prob_dir)
                    problems.append(meta)
                except Exception:
                    continue

        problems.sort(key=lambda x: x.get("id", ""))
        return problems

    def _load_indexed(self) -> Optional[List[Dict[str, Any]]]:
        try:
            from tutor.db import CatalogIndex

            index = CatalogIndex()
            index.sync(self.search_paths)
            problems = index.all_problems()
            index.close()
            for p in problems:
                _normalize_meta(p, Path(p["dir"]))
            return problems
        except Exception:
            return None

    def list_problems(self) -> List[Dict[str, Any]]:
        problems = self._load_indexed()
        if problems is None:
            problems = self._scan_filesystem()

        for p in problems:
            p["solved"] = is_solved(p.get("id", ""))

        # Resolve DAG unlock status
        solved_map = {p["id"]: p["solved"] for p in problems}
        progress = get_progress()

        for p in problems:
            deps = p.get("depends_on", [])
            missing = [
                dep for dep in deps
                if not (solved_map.get(dep, False) or is_solved(dep))
            ]
            p["missing_deps"] = missing
            p["unlocked"] = len(missing) == 0
            p["progress"] = progress.get(p["id"], {})

        return problems

    def get_problem(self, problem_id_or_num: str) -> Optional[Dict[str, Any]]:
        problems = self.list_problems()
        query = str(problem_id_or_num).strip()
        for p in problems:
            pid = p.get("id", "")
            if pid == query:
                return p
            if pid.startswith(f"{query.zfill(3)}-"):
                return p
            prefix = pid.split("-")[0].lstrip("0") or "0"
            q_strip = query.lstrip("0") or "0"
            if prefix == q_strip and query.isdigit():
                return p
        return None
