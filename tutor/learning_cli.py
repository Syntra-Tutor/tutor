"""CLI for tutor's optional knowledge/evidence/learning-path subsystem."""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

try:
    from . import learning as core
except ImportError:
    import learning as core


def _json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser():
    p=argparse.ArgumentParser(prog="tutor-learning", description="Knowledge graph, learner evidence, and editable learning paths")
    p.add_argument("--db", default=os.environ.get("TUTOR_LEARNING_DB", ".tutor/learning.sqlite3"), help="SQLite database (default: .tutor/learning.sqlite3)")
    sub=p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="initialize the local learning database")

    pkg=sub.add_parser("package"); ps=pkg.add_subparsers(dest="action",required=True)
    pa=ps.add_parser("add"); pa.add_argument("id"); pa.add_argument("title"); pa.add_argument("--version",default="0.1.0"); pa.add_argument("--source",default="")

    comp=sub.add_parser("component"); cs=comp.add_subparsers(dest="action",required=True)
    ca=cs.add_parser("add"); ca.add_argument("id"); ca.add_argument("label"); ca.add_argument("--kind",default="unspecified",help="free-form descriptor; no fixed taxonomy"); ca.add_argument("--package"); ca.add_argument("--description",default="")
    cs.add_parser("list")

    rel=sub.add_parser("relation"); rs=rel.add_subparsers(dest="action",required=True)
    ra=rs.add_parser("add"); ra.add_argument("source"); ra.add_argument("target"); ra.add_argument("type",help="e.g. requires, recommends, refines, adjacent, part_of, equivalent, related"); ra.add_argument("--strength",default="unspecified"); ra.add_argument("--notes",default="")
    rl=rs.add_parser("list"); rl.add_argument("--component")

    prob=sub.add_parser("problem"); prs=prob.add_subparsers(dest="action",required=True)
    pl=prs.add_parser("link"); pl.add_argument("problem_id"); pl.add_argument("component_id"); pl.add_argument("--role",required=True,choices=["introduces","exercises","assesses","applies"]); pl.add_argument("--notes",default="")

    ev=sub.add_parser("evidence"); es=ev.add_subparsers(dest="action",required=True)
    er=es.add_parser("record"); er.add_argument("component_id"); er.add_argument("--outcome",required=True,choices=["attempted","partial","demonstrated","strong"]); er.add_argument("--problem"); er.add_argument("--method",default="manual"); er.add_argument("--confidence",type=float); er.add_argument("--notes",default="")
    el=es.add_parser("list"); el.add_argument("--component")

    ref=sub.add_parser("reference"); refs=ref.add_subparsers(dest="action",required=True)
    radd=refs.add_parser("add"); radd.add_argument("title"); radd.add_argument("url"); radd.add_argument("--component"); radd.add_argument("--problem"); radd.add_argument("--source",default=""); radd.add_argument("--notes",default="")
    rlist=refs.add_parser("list"); rlist.add_argument("--component"); rlist.add_argument("--problem")

    path=sub.add_parser("path"); paths=path.add_subparsers(dest="action",required=True)
    pc=paths.add_parser("create"); pc.add_argument("id"); pc.add_argument("title"); pc.add_argument("--description",default=""); pc.add_argument("--origin",choices=["author","learner","tutor"],default="learner")
    paths.add_parser("list")
    pshow=paths.add_parser("show"); pshow.add_argument("id")
    padd=paths.add_parser("add"); padd.add_argument("id"); padd.add_argument("problem_id"); padd.add_argument("--label",default=""); padd.add_argument("--after")
    prem=paths.add_parser("remove"); prem.add_argument("id"); prem.add_argument("problem_id")
    pmove=paths.add_parser("move"); pmove.add_argument("id"); pmove.add_argument("problem_id"); pmove.add_argument("--after")
    pstate=paths.add_parser("state"); pstate.add_argument("id"); pstate.add_argument("problem_id"); pstate.add_argument("state",choices=["planned","in_progress","completed","skipped"])
    pn=paths.add_parser("next"); pn.add_argument("id")
    psuggest=paths.add_parser("suggest"); psuggest.add_argument("id"); psuggest.add_argument("--limit",type=int,default=5)

    proposal=sub.add_parser("proposal"); props=proposal.add_subparsers(dest="action",required=True)
    pshow2=props.add_parser("show"); pshow2.add_argument("id")
    for act in ("add","remove","move"):
        pe=props.add_parser(act); pe.add_argument("id"); pe.add_argument("problem_id"); pe.add_argument("--label",default=""); pe.add_argument("--after")
    pac=props.add_parser("accept"); pac.add_argument("id")
    pre=props.add_parser("reject"); pre.add_argument("id")
    return p


def run(a):
    db=a.db
    if a.command=="init": core.initialize(db); print(f"Initialized {db}")
    elif a.command=="package" and a.action=="add": core.add_package(db,a.id,a.title,a.version,a.source); print(f"Package saved: {a.id}")
    elif a.command=="component":
        if a.action=="add": core.add_component(db,a.id,a.label,a.kind,a.package,a.description); print(f"Component saved: {a.id}")
        else: _json(core.list_components(db))
    elif a.command=="relation":
        if a.action=="add": core.add_relation(db,a.source,a.target,a.type,a.strength,a.notes); print("Relation saved")
        else: _json(core.list_relations(db,a.component))
    elif a.command=="problem": core.link_problem(db,a.problem_id,a.component_id,a.role,a.notes); print("Problem/component link saved")
    elif a.command=="evidence":
        if a.action=="record": print(f"Evidence recorded: #{core.record_evidence(db,a.component_id,a.outcome,a.problem,a.method,a.confidence,a.notes)}")
        else: _json(core.list_evidence(db,a.component))
    elif a.command=="reference":
        if a.action=="add":
            if not a.component and not a.problem: raise ValueError("specify --component and/or --problem")
            core.add_reference(db,a.title,a.url,a.component,a.problem,a.source,a.notes); print("Reference saved")
        else: _json(core.list_references(db,a.component,a.problem))
    elif a.command=="path":
        if a.action=="create": core.create_path(db,a.id,a.title,a.description,a.origin); print(f"Path created: {a.id}")
        elif a.action=="list": _json(core.list_paths(db))
        elif a.action=="show": _json(core.path_data(db,a.id))
        elif a.action in {"add","remove","move"}:
            core.edit_path(db,a.id,a.action,a.problem_id,getattr(a,"label",""),getattr(a,"after",None)); print("Path updated")
        elif a.action=="state": core.mark_path_item(db,a.id,a.problem_id,a.state); print("Path item state updated")
        elif a.action=="next":
            item=core.next_item(db,a.id)
            if item: _json(item)
            else: print("No pending item in this path")
        elif a.action=="suggest":
            proposal_id=core.propose_path(db,a.id,a.limit); _json(core.get_proposal(db,proposal_id))
    elif a.command=="proposal":
        if a.action=="show": _json(core.get_proposal(db,a.id))
        elif a.action in {"add","remove","move"}:
            core.edit_proposal(db,a.id,a.action,a.problem_id,a.label,a.after); print("Proposal edited; active path unchanged")
        elif a.action=="accept": core.decide_proposal(db,a.id,True); print("Proposal accepted; active learning path updated")
        elif a.action=="reject": core.decide_proposal(db,a.id,False); print("Proposal rejected; active path unchanged")


def main(argv=None):
    parser=build_parser(); args=parser.parse_args(argv)
    try: run(args)
    except (ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}",file=sys.stderr); return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
