"""Problem template scaffolding (issue #36).

Defines the canonical ``problem.json`` schema and generates new problem
directories from it, so contributors don't hand-craft metadata and drift.

Schema fields (all problems in the repo currently carry these ten keys):

    id          directory name / unique identifier, e.g. "079-new-problem"
    title       human-readable one-liner
    track       coarse curriculum grouping shown in `tutor list`
    category    skill category used for grouping & recommendations
    difficulty  one of EASY | MEDIUM | HARD
    depends_on  list of prerequisite problem ids (DAG edges)
    tags        free-form keyword list
    colspec     leaderboard column spec: [{"hdr": str, "asc": bool}, ...]
    languages   supported language dirs, e.g. ["cpp"]
    spec        markdown problem statement shown to the student
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBLEMS_DIR = REPO_ROOT / "problems"

DIFFICULTIES = ("Easy", "Medium", "Hard")

DEFAULT_COLSPEC = [
    {"hdr": "Score", "asc": False},
    {"hdr": "Cycles/Op", "asc": True},
    {"hdr": "Bytes", "asc": True},
]

_ID_RE = re.compile(r"^[0-9]{3}[a-z]?-[a-z0-9]+(?:-[a-z0-9]+)*$")

_CPP_STUB_NAME = "solution_stub.hpp"

# Students always work in `solution.hpp` (the workspace copies the stub to
# that name), so harnesses include it directly. The scaffold ships a minimal
# solution.hpp too, so a freshly created problem compiles and passes out of
# the box — authors iterate from green, not from a broken build.
_CPP_SOLUTION_NAME = "solution.hpp"
_CPP_SOLUTION_TEMPLATE = """#pragma once
// {problem_id}: {title}
// Reference/skeleton implementation students receive as their starting point.

#include <cstdint>
#include <string>
#include <vector>
"""

# Makefile shipped with every scaffolded cpp problem. Matches the layout the
# test runner expects (compiles solution.hpp against the locked harness.cpp).
_CPP_MAKEFILE = """CXX ?= g++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -pthread -I.

.PHONY: test clean

test: harness_bin
\t./harness_bin

harness_bin: harness.cpp solution.hpp
\t$(CXX) $(CXXFLAGS) harness.cpp -o harness_bin

clean:
\trm -f harness_bin
"""


def next_problem_id(problems_dir: Path = PROBLEMS_DIR) -> str:
    """Suggest the next numeric problem id prefix (e.g. '079')."""
    highest = -1
    if problems_dir.exists():
        for d in problems_dir.iterdir():
            m = re.match(r"^(\d{3})", d.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return f"{highest + 1:03d}"


def normalize_problem_id(problem_id: str, problems_dir: Path = PROBLEMS_DIR) -> str:
    """Accept a bare kebab-case slug and auto-prefix the next number.

    ``lockfree-stack`` -> ``079-lockfree-stack``. Ids that already start with
    three digits are returned unchanged (after trimming whitespace).
    """
    pid = problem_id.strip().lower()
    if re.match(r"^\d{3}", pid):
        return pid
    slug = re.sub(r"[^a-z0-9]+", "-", pid).strip("-")
    if not slug:
        raise ValueError(f"cannot derive a problem slug from {problem_id!r}")
    return f"{next_problem_id(problems_dir)}-{slug}"


def validate_meta(meta: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable schema errors (empty == valid)."""
    errors: List[str] = []
    required = ["id", "title", "track", "category", "difficulty",
                "depends_on", "tags", "colspec", "languages", "spec"]
    for key in required:
        if key not in meta:
            errors.append(f"missing required field: {key!r}")

    pid = meta.get("id", "")
    if pid and not _ID_RE.match(pid):
        errors.append(
            f"id {pid!r} must match NNN[-suffix] (3 digits, optional letter, "
            "then kebab-case words), e.g. '079-lockfree-stack'"
        )

    diff = meta.get("difficulty")
    if diff is not None:
        # Accept any case; canonicalize later
        if str(diff).title() not in DIFFICULTIES:
            errors.append(f"difficulty {diff!r} must be one of {list(DIFFICULTIES)}")

    deps = meta.get("depends_on")
    if deps is not None and (not isinstance(deps, list) or any(not isinstance(x, str) for x in deps)):
        errors.append("depends_on must be a list of problem id strings")

    langs = meta.get("languages")
    if langs is not None and (not isinstance(langs, list) or not langs):
        errors.append("languages must be a non-empty list, e.g. ['cpp']")

    colspec = meta.get("colspec")
    if colspec is not None:
        if not isinstance(colspec, list) or not all(
            isinstance(c, dict) and "hdr" in c and "asc" in c for c in colspec
        ):
            errors.append('colspec entries must be objects like {"hdr": "Score", "asc": false}')

    if not meta.get("spec", "").strip():
        errors.append("spec (markdown problem statement) must not be empty")

    return errors


def build_meta(
    problem_id: str,
    title: str,
    difficulty: str = "Medium",
    category: str = "",
    track: str = "",
    tags: Optional[List[str]] = None,
    depends_on: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    spec: str = "",
) -> Dict[str, Any]:
    """Assemble a defaults-filled problem metadata dict."""
    category = category or "Systems"
    difficulty = str(difficulty).title() if difficulty else "Medium"
    if difficulty not in DIFFICULTIES:
        difficulty = "Medium"
    return {
        "id": problem_id,
        "title": title,
        "track": track or category,
        "category": category,
        "difficulty": difficulty,
        "depends_on": depends_on or [],
        "tags": tags or [],
        "colspec": DEFAULT_COLSPEC,
        "languages": languages or ["cpp"],
        "spec": spec or _default_spec(problem_id, title),
    }


def _default_spec(problem_id: str, title: str) -> str:
    return (
        f"# {problem_id}: {title}\n\n"
        "## Problem Statement\n\n"
        "<!-- Describe the problem the student must solve. -->\n\n"
        "## Requirements\n\n"
        "1. TODO: state the exact function signatures and behavior.\n\n"
        "## Constraints\n\n"
        "- TODO: complexity / correctness constraints judged by the harness.\n"
    )


_CPP_STUB_TEMPLATE = """#pragma once
// {problem_id}: {title}
// Student solution goes here. Do not modify the harness.

#include <cstdint>
#include <string>
#include <vector>
"""

_CPP_HARNESS_TEMPLATE = """// LOCKED — do not modify. Judges {problem_id}.
#include "solution.hpp"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <iostream>

int main() {{
    std::cout << "=== Running {problem_id} Test Suite ===\\n";

    // TODO: add assertions against the required API, e.g.:
    // assert(solution_fn(input) == expected);

    std::cout << "ALL TESTS PASSED" << std::endl;
    return EXIT_SUCCESS;
}}
"""


def scaffold_problem(
    problem_id: str,
    title: str,
    problems_dir: Path = PROBLEMS_DIR,
    **meta_kwargs,
) -> Path:
    """Create ``problems/<id>/problem.json`` plus C++ stub/harness skeletons.

    Raises ``FileExistsError`` if the problem already exists and ``ValueError``
    with the full error list if the generated metadata fails validation.
    """
    meta = build_meta(problem_id, title, **meta_kwargs)
    errors = validate_meta(meta)
    if errors:
        raise ValueError("invalid problem metadata:\n  - " + "\n  - ".join(errors))

    prob_dir = problems_dir / problem_id
    if prob_dir.exists():
        raise FileExistsError(f"{prob_dir} already exists")

    lang_dirs = meta["languages"]
    if "cpp" in lang_dirs:
        cpp_dir = prob_dir / "cpp"
        cpp_dir.mkdir(parents=True)
        (cpp_dir / _CPP_STUB_NAME).write_text(
            _CPP_STUB_TEMPLATE.format(problem_id=problem_id, title=title)
        )
        (cpp_dir / _CPP_SOLUTION_NAME).write_text(
            _CPP_SOLUTION_TEMPLATE.format(problem_id=problem_id, title=title)
        )
        (cpp_dir / "harness.cpp").write_text(
            _CPP_HARNESS_TEMPLATE.format(problem_id=problem_id)
        )
        (cpp_dir / "Makefile").write_text(_CPP_MAKEFILE)
    else:
        prob_dir.mkdir(parents=True)

    (prob_dir / "problem.json").write_text(json.dumps(meta, indent=2) + "\n")
    return prob_dir


class Watcher:
    """Lightweight mtime poller that fires a callback when files change.

    Used by ``tutor watch`` to revalidate the catalog on save, so authors get
    instant feedback without re-running ``tutor validate`` by hand. Uses only
    the stdlib (os.stat polling) to keep the zero-dependency promise.
    """

    def __init__(self, paths, interval: float = 0.5):
        self._paths = [Path(p) for p in paths]
        self._interval = interval
        self._stamps = {}

    def _snapshot(self) -> dict:
        stamps = {}
        for base in self._paths:
            if not base.exists():
                continue
            if base.is_file():
                try:
                    stamps[str(base)] = base.stat().st_mtime_ns
                except OSError:
                    pass
                continue
            for f in base.rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts:
                    try:
                        stamps[str(f)] = f.stat().st_mtime_ns
                    except OSError:
                        pass
        return stamps

    def poll(self):
        """Return the set of changed/added/removed paths since last poll."""
        now = self._snapshot()
        changed = {
            p for p, t in now.items() if self._stamps.get(p) != t
        } | {p for p in self._stamps if p not in now}
        self._stamps = now
        return changed

    def wait_for_change(self):
        """Block until at least one tracked path changes; return those paths."""
        import time

        while True:
            changed = self.poll()
            if changed:
                return changed
            time.sleep(self._interval)
