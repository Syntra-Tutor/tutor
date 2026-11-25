"""Local knowledge graph, learner evidence, and editable learning paths for tutor.

Standard-library only. All tables are namespaced with tutor_ so this can share an
existing SQLite catalog database without colliding with its schema.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def initialize(db_path: str | Path) -> None:
    with connect(db_path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tutor_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tutor_packages (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '0.1.0',
            source TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tutor_components (
            id TEXT PRIMARY KEY,
            package_id TEXT REFERENCES tutor_packages(id) ON DELETE SET NULL,
            label TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'unspecified',
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tutor_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL REFERENCES tutor_components(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES tutor_components(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            strength TEXT NOT NULL DEFAULT 'unspecified',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(source_id, target_id, relation_type)
        );
        CREATE INDEX IF NOT EXISTS tutor_relations_source ON tutor_relations(source_id);
        CREATE INDEX IF NOT EXISTS tutor_relations_target ON tutor_relations(target_id);
        CREATE TABLE IF NOT EXISTS tutor_problem_components (
            problem_id TEXT NOT NULL,
            component_id TEXT NOT NULL REFERENCES tutor_components(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            PRIMARY KEY(problem_id, component_id, role)
        );
        CREATE INDEX IF NOT EXISTS tutor_problem_components_component
            ON tutor_problem_components(component_id);
        CREATE TABLE IF NOT EXISTS tutor_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component_id TEXT NOT NULL REFERENCES tutor_components(id) ON DELETE CASCADE,
            problem_id TEXT,
            method TEXT NOT NULL DEFAULT 'manual',
            outcome TEXT NOT NULL CHECK(outcome IN ('attempted','partial','demonstrated','strong')),
            confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            notes TEXT NOT NULL DEFAULT '',
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS tutor_evidence_component_date
            ON tutor_evidence(component_id, recorded_at DESC, id DESC);
        CREATE TABLE IF NOT EXISTS tutor_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            component_id TEXT REFERENCES tutor_components(id) ON DELETE CASCADE,
            problem_id TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            CHECK(component_id IS NOT NULL OR problem_id IS NOT NULL)
        );
        CREATE TABLE IF NOT EXISTS tutor_paths (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            origin TEXT NOT NULL DEFAULT 'learner',
            revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tutor_path_items (
            path_id TEXT NOT NULL REFERENCES tutor_paths(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            problem_id TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'planned'
                CHECK(state IN ('planned','in_progress','completed','skipped')),
            notes TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(path_id, position),
            UNIQUE(path_id, problem_id)
        );
        CREATE TABLE IF NOT EXISTS tutor_path_proposals (
            id TEXT PRIMARY KEY,
            path_id TEXT NOT NULL REFERENCES tutor_paths(id) ON DELETE CASCADE,
            base_revision INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','accepted','rejected','stale')),
            rationale TEXT NOT NULL DEFAULT '',
            items_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_at TEXT
        );
        """)
        db.execute("INSERT OR REPLACE INTO tutor_meta(key,value) VALUES('schema_version',?)",
                   (str(SCHEMA_VERSION),))


def _required(value: str, name: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def add_package(db_path: str | Path, package_id: str, title: str,
                version: str = "0.1.0", source: str = "") -> None:
    initialize(db_path)
    with connect(db_path) as db:
        db.execute("""INSERT INTO tutor_packages(id,title,version,source,created_at)
            VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,
            version=excluded.version, source=excluded.source""",
            (_required(package_id,"package id"), _required(title,"title"), version, source, utcnow()))


def add_component(db_path: str | Path, component_id: str, label: str,
                  kind: str = "unspecified", package_id: str | None = None,
                  description: str = "") -> None:
    initialize(db_path)
    now = utcnow()
    with connect(db_path) as db:
        db.execute("""INSERT INTO tutor_components
            (id,package_id,label,kind,description,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            package_id=excluded.package_id,label=excluded.label,kind=excluded.kind,
            description=excluded.description,updated_at=excluded.updated_at""",
            (_required(component_id,"component id"), package_id, _required(label,"label"),
             kind or "unspecified", description, now, now))


def _would_cycle(db: sqlite3.Connection, source: str, target: str) -> bool:
    if source == target:
        return True
    # A -> B means B is required by A. Detect a path from target back to source.
    row = db.execute("""WITH RECURSIVE reachable(id) AS (
        SELECT target_id FROM tutor_relations
          WHERE source_id=? AND relation_type='requires'
        UNION
        SELECT r.target_id FROM tutor_relations r JOIN reachable x ON r.source_id=x.id
          WHERE r.relation_type='requires'
    ) SELECT 1 FROM reachable WHERE id=? LIMIT 1""", (target, source)).fetchone()
    return row is not None


def add_relation(db_path: str | Path, source: str, target: str,
                 relation_type: str, strength: str = "unspecified", notes: str = "") -> None:
    initialize(db_path)
    source, target = _required(source,"source id"), _required(target,"target id")
    relation_type = _required(relation_type,"relation type").lower().replace(" ", "_")
    with connect(db_path) as db:
        for component in (source, target):
            if not db.execute("SELECT 1 FROM tutor_components WHERE id=?", (component,)).fetchone():
                raise ValueError(f"unknown knowledge component: {component}")
        # Required-prerequisite edges must be acyclic. Other knowledge relations may cycle.
        if relation_type == "requires" and _would_cycle(db, source, target):
            raise ValueError("adding this 'requires' relation would create a prerequisite cycle")
        db.execute("""INSERT INTO tutor_relations
            (source_id,target_id,relation_type,strength,notes,created_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,target_id,relation_type)
            DO UPDATE SET strength=excluded.strength,notes=excluded.notes""",
            (source,target,relation_type,strength,notes,utcnow()))


def link_problem(db_path: str | Path, problem_id: str, component_id: str,
                 role: str, notes: str = "") -> None:
    initialize(db_path)
    role = _required(role,"role").lower()
    if role not in {"introduces","exercises","assesses","applies"}:
        raise ValueError("role must be introduces, exercises, assesses, or applies")
    with connect(db_path) as db:
        db.execute("""INSERT OR REPLACE INTO tutor_problem_components
            (problem_id,component_id,role,notes,created_at) VALUES(?,?,?,?,?)""",
            (_required(problem_id,"problem id"), _required(component_id,"component id"), role,
             notes, utcnow()))


def record_evidence(db_path: str | Path, component_id: str, outcome: str,
                    problem_id: str | None = None, method: str = "manual",
                    confidence: float | None = None, notes: str = "") -> int:
    initialize(db_path)
    outcome = _required(outcome,"outcome").lower()
    if outcome not in {"attempted","partial","demonstrated","strong"}:
        raise ValueError("outcome must be attempted, partial, demonstrated, or strong")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    with connect(db_path) as db:
        cur = db.execute("""INSERT INTO tutor_evidence
            (component_id,problem_id,method,outcome,confidence,notes,recorded_at)
            VALUES(?,?,?,?,?,?,?)""",
            (_required(component_id,"component id"), problem_id, method, outcome,
             confidence, notes, utcnow()))
        return int(cur.lastrowid)


def add_reference(db_path: str | Path, title: str, url: str,
                  component_id: str | None = None, problem_id: str | None = None,
                  source: str = "", notes: str = "") -> None:
    initialize(db_path)
    url = _required(url,"URL")
    if not url.startswith(("https://", "http://")):
        raise ValueError("URL must begin with http:// or https://")
    with connect(db_path) as db:
        db.execute("""INSERT INTO tutor_references
            (title,url,source,component_id,problem_id,notes,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (_required(title,"title"), url, source, component_id, problem_id, notes, utcnow()))


def create_path(db_path: str | Path, path_id: str, title: str,
                description: str = "", origin: str = "learner") -> None:
    initialize(db_path)
    with connect(db_path) as db:
        db.execute("""INSERT INTO tutor_paths(id,title,description,origin,created_at,updated_at)
            VALUES(?,?,?,?,?,?)""",
            (_required(path_id,"path id"), _required(title,"title"), description, origin, utcnow(), utcnow()))


def _items(db: sqlite3.Connection, path_id: str) -> list[dict[str, Any]]:
    rows = db.execute("""SELECT problem_id,label,state,notes FROM tutor_path_items
        WHERE path_id=? ORDER BY position""", (path_id,)).fetchall()
    return [dict(r) for r in rows]


def _save_items(db: sqlite3.Connection, path_id: str, items: list[dict[str, Any]]) -> None:
    seen = set()
    for item in items:
        problem_id = _required(str(item["problem_id"]),"problem id")
        if problem_id in seen:
            raise ValueError(f"problem appears more than once in path: {problem_id}")
        seen.add(problem_id)
    db.execute("DELETE FROM tutor_path_items WHERE path_id=?", (path_id,))
    db.executemany("""INSERT INTO tutor_path_items
        (path_id,position,problem_id,label,state,notes) VALUES(?,?,?,?,?,?)""",
        [(path_id,i,x["problem_id"],x.get("label", ""),x.get("state","planned"),x.get("notes",""))
         for i,x in enumerate(items)])
    db.execute("UPDATE tutor_paths SET revision=revision+1,updated_at=? WHERE id=?", (utcnow(),path_id))


def edit_path(db_path: str | Path, path_id: str, action: str, problem_id: str,
              label: str = "", after: str | None = None) -> None:
    initialize(db_path)
    with connect(db_path) as db:
        if not db.execute("SELECT 1 FROM tutor_paths WHERE id=?", (path_id,)).fetchone():
            raise ValueError(f"unknown path: {path_id}")
        items = _items(db,path_id)
        idx = next((i for i,x in enumerate(items) if x["problem_id"]==problem_id),None)
        if action == "add":
            if idx is not None:
                raise ValueError(f"problem already in path: {problem_id}")
            item = {"problem_id":problem_id,"label":label,"state":"planned","notes":""}
            insert_at = len(items)
            if after:
                after_idx = next((i for i,x in enumerate(items) if x["problem_id"]==after),None)
                if after_idx is None: raise ValueError(f"--after problem is not in path: {after}")
                insert_at = after_idx+1
            items.insert(insert_at,item)
        elif action == "remove":
            if idx is None: raise ValueError(f"problem not in path: {problem_id}")
            items.pop(idx)
        elif action == "move":
            if idx is None: raise ValueError(f"problem not in path: {problem_id}")
            item = items.pop(idx)
            insert_at = 0
            if after:
                after_idx = next((i for i,x in enumerate(items) if x["problem_id"]==after),None)
                if after_idx is None: raise ValueError(f"--after problem is not in path: {after}")
                insert_at = after_idx+1
            items.insert(insert_at,item)
        else:
            raise ValueError(f"unknown path edit: {action}")
        _save_items(db,path_id,items)


def mark_path_item(db_path: str | Path, path_id: str, problem_id: str, state: str) -> None:
    if state not in {"planned","in_progress","completed","skipped"}:
        raise ValueError("invalid path item state")
    initialize(db_path)
    with connect(db_path) as db:
        cur=db.execute("UPDATE tutor_path_items SET state=? WHERE path_id=? AND problem_id=?",
                       (state,path_id,problem_id))
        if cur.rowcount == 0: raise ValueError(f"problem not in path: {problem_id}")
        db.execute("UPDATE tutor_paths SET revision=revision+1,updated_at=? WHERE id=?",(utcnow(),path_id))


def _latest_evidence(db: sqlite3.Connection, component_id: str) -> dict[str, Any] | None:
    row=db.execute("""SELECT outcome,confidence,method,recorded_at,problem_id FROM tutor_evidence
        WHERE component_id=? ORDER BY recorded_at DESC,id DESC LIMIT 1""",(component_id,)).fetchone()
    return dict(row) if row else None


def propose_path(db_path: str | Path, path_id: str, limit: int = 5) -> str:
    """Generate a proposal from unplanned problem/component links and latest evidence.

    This is deliberately a transparent heuristic, not a mastery claim. The active
    path is never changed until the learner explicitly accepts the proposal.
    """
    initialize(db_path)
    if limit < 1: raise ValueError("limit must be positive")
    with connect(db_path) as db:
        path=db.execute("SELECT revision FROM tutor_paths WHERE id=?",(path_id,)).fetchone()
        if not path: raise ValueError(f"unknown path: {path_id}")
        current=_items(db,path_id)
        already={x["problem_id"] for x in current}
        rows=db.execute("""SELECT pc.problem_id,pc.component_id,pc.role,c.label
            FROM tutor_problem_components pc JOIN tutor_components c ON c.id=pc.component_id
            ORDER BY pc.problem_id,pc.component_id""").fetchall()
        candidates: dict[str,dict[str,Any]]={}
        outcome_weight={"attempted":3.0,"partial":5.0,"demonstrated":0.5,"strong":0.0}
        for row in rows:
            pid=row["problem_id"]
            if pid in already: continue
            info=candidates.setdefault(pid,{"score":0.0,"reasons":[],"labels":[]})
            ev=_latest_evidence(db,row["component_id"])
            if ev is None:
                score=2.5 if row["role"] in {"introduces","exercises","assesses"} else 1.5
                reason=f"no recorded evidence for {row['label']}"
            else:
                score=outcome_weight[ev["outcome"]]
                if ev["confidence"] is not None:
                    score += (1.0-ev["confidence"])*1.5
                reason=f"latest evidence for {row['label']}: {ev['outcome']}"
            if row["role"]=="assesses": score += 0.8
            elif row["role"]=="exercises": score += 0.5
            info["score"] += score
            info["reasons"].append(reason)
            info["labels"].append(row["label"])
        ranked=sorted(candidates.items(), key=lambda pair:(-pair[1]["score"],pair[0]))[:limit]
        proposal_items=[dict(x) for x in current]
        for pid,info in ranked:
            label=", ".join(dict.fromkeys(info["labels"]))
            proposal_items.append({"problem_id":pid,"label":label,"state":"planned",
                                   "notes":"Tutor suggestion: "+"; ".join(dict.fromkeys(info["reasons"]))})
        if not ranked:
            rationale=("No additional linked problems were found. Link problems to knowledge "
                       "components with `problem link` before generating path suggestions.")
        else:
            rationale="Suggested from problem/component links and latest learner evidence. " + " ".join(
                f"{pid}: {', '.join(dict.fromkeys(info['reasons']))}." for pid,info in ranked)
        import uuid
        proposal_id="proposal-"+uuid.uuid4().hex[:10]
        db.execute("""INSERT INTO tutor_path_proposals
            (id,path_id,base_revision,status,rationale,items_json,created_at)
            VALUES(?,?,?,'pending',?,?,?)""",
            (proposal_id,path_id,int(path["revision"]),rationale,json.dumps(proposal_items),utcnow()))
        return proposal_id


def edit_proposal(db_path: str | Path, proposal_id: str, action: str, problem_id: str,
                  label: str = "", after: str | None = None) -> None:
    initialize(db_path)
    with connect(db_path) as db:
        row=db.execute("SELECT * FROM tutor_path_proposals WHERE id=?",(proposal_id,)).fetchone()
        if not row: raise ValueError(f"unknown proposal: {proposal_id}")
        if row["status"]!="pending": raise ValueError("only pending proposals can be edited")
        items=json.loads(row["items_json"])
        idx=next((i for i,x in enumerate(items) if x["problem_id"]==problem_id),None)
        if action=="add":
            if idx is not None: raise ValueError(f"problem already in proposal: {problem_id}")
            item={"problem_id":problem_id,"label":label,"state":"planned","notes":"Learner-added"}
            pos=len(items)
            if after:
                j=next((i for i,x in enumerate(items) if x["problem_id"]==after),None)
                if j is None: raise ValueError(f"--after problem not found: {after}")
                pos=j+1
            items.insert(pos,item)
        elif action=="remove":
            if idx is None: raise ValueError(f"problem not in proposal: {problem_id}")
            items.pop(idx)
        elif action=="move":
            if idx is None: raise ValueError(f"problem not in proposal: {problem_id}")
            item=items.pop(idx); pos=0
            if after:
                j=next((i for i,x in enumerate(items) if x["problem_id"]==after),None)
                if j is None: raise ValueError(f"--after problem not found: {after}")
                pos=j+1
            items.insert(pos,item)
        else: raise ValueError(action)
        _save_items_no_revision(db,proposal_id,items)


def _save_items_no_revision(db: sqlite3.Connection, proposal_id: str, items: list[dict[str,Any]]) -> None:
    seen=set()
    for x in items:
        if x["problem_id"] in seen: raise ValueError(f"duplicate problem: {x['problem_id']}")
        seen.add(x["problem_id"])
    db.execute("UPDATE tutor_path_proposals SET items_json=? WHERE id=?",(json.dumps(items),proposal_id))


def decide_proposal(db_path: str | Path, proposal_id: str, accept: bool) -> None:
    initialize(db_path)
    with connect(db_path) as db:
        p=db.execute("SELECT * FROM tutor_path_proposals WHERE id=?",(proposal_id,)).fetchone()
        if not p: raise ValueError(f"unknown proposal: {proposal_id}")
        if p["status"]!="pending": raise ValueError(f"proposal is already {p['status']}")
        if accept:
            path=db.execute("SELECT revision FROM tutor_paths WHERE id=?",(p["path_id"],)).fetchone()
            if not path or int(path["revision"])!=int(p["base_revision"]):
                db.execute("UPDATE tutor_path_proposals SET status='stale',decided_at=? WHERE id=?",
                           (utcnow(),proposal_id))
                db.commit()
                raise ValueError("path changed since this proposal was generated; generate a fresh proposal")
            items=json.loads(p["items_json"])
            _save_items(db,p["path_id"],items)
            db.execute("UPDATE tutor_path_proposals SET status='accepted',decided_at=? WHERE id=?",
                       (utcnow(),proposal_id))
        else:
            db.execute("UPDATE tutor_path_proposals SET status='rejected',decided_at=? WHERE id=?",
                       (utcnow(),proposal_id))


def get_proposal(db_path: str | Path, proposal_id: str) -> dict[str,Any]:
    initialize(db_path)
    with connect(db_path) as db:
        row=db.execute("SELECT * FROM tutor_path_proposals WHERE id=?",(proposal_id,)).fetchone()
        if not row: raise ValueError(f"unknown proposal: {proposal_id}")
        result=dict(row); result["items"]=json.loads(result.pop("items_json")); return result


def path_data(db_path: str | Path, path_id: str) -> dict[str,Any]:
    initialize(db_path)
    with connect(db_path) as db:
        row=db.execute("SELECT * FROM tutor_paths WHERE id=?",(path_id,)).fetchone()
        if not row: raise ValueError(f"unknown path: {path_id}")
        result=dict(row); result["items"]=_items(db,path_id); return result


def list_paths(db_path: str | Path) -> list[dict[str,Any]]:
    initialize(db_path)
    with connect(db_path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM tutor_paths ORDER BY title,id")]


def list_components(db_path: str | Path) -> list[dict[str,Any]]:
    initialize(db_path)
    with connect(db_path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM tutor_components ORDER BY id")]


def list_relations(db_path: str | Path, component_id: str | None = None) -> list[dict[str,Any]]:
    initialize(db_path)
    with connect(db_path) as db:
        if component_id:
            rows=db.execute("SELECT * FROM tutor_relations WHERE source_id=? OR target_id=? ORDER BY relation_type",
                            (component_id,component_id))
        else:
            rows=db.execute("SELECT * FROM tutor_relations ORDER BY source_id,relation_type,target_id")
        return [dict(r) for r in rows]


def list_references(db_path: str | Path, component_id: str | None = None,
                    problem_id: str | None = None) -> list[dict[str,Any]]:
    initialize(db_path)
    query="SELECT * FROM tutor_references WHERE 1=1"; args=[]
    if component_id: query+=" AND component_id=?"; args.append(component_id)
    if problem_id: query+=" AND problem_id=?"; args.append(problem_id)
    query+=" ORDER BY title"
    with connect(db_path) as db: return [dict(r) for r in db.execute(query,args)]


def list_evidence(db_path: str | Path, component_id: str | None = None) -> list[dict[str,Any]]:
    initialize(db_path)
    with connect(db_path) as db:
        if component_id:
            rows=db.execute("SELECT * FROM tutor_evidence WHERE component_id=? ORDER BY recorded_at DESC,id DESC",(component_id,))
        else: rows=db.execute("SELECT * FROM tutor_evidence ORDER BY recorded_at DESC,id DESC")
        return [dict(r) for r in rows]


def next_item(db_path: str | Path, path_id: str) -> dict[str,Any] | None:
    data=path_data(db_path,path_id)
    return next((x for x in data["items"] if x["state"] in {"planned","in_progress"}),None)
