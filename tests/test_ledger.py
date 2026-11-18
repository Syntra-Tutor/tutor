import json
import tempfile
import unittest
from pathlib import Path

from tutor.ledger import LedgerError, append_completions, read_events
from tutor.scoreboard import fold_events, merge_scoreboard_entries


def entry(user, cycles, solution, when="2026-01-01T00:00:00+00:00"):
    return {
        "user": user,
        "problem_id": "000a-hello-world",
        "problem_hash": "p1",
        "solution_sha256": solution,
        "score": 100.0,
        "scoreboard": [100.0, cycles, 10],
        "submitted_at": when,
    }


class LedgerTests(unittest.TestCase):
    def test_repeated_claim_is_ignored_and_fold_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "completions.jsonl"
            self.assertEqual(len(append_completions([entry("a", 5.0, "s1")], path)), 1)
            self.assertEqual(append_completions([entry("a", 5.0, "s1")], path), [])
            append_completions([entry("b", 2.0, "s2", "2026-01-02T00:00:00+00:00")], path)
            events = read_events(path)
            board = fold_events(events)
        self.assertEqual(board, fold_events(events))
        rows = board["problems"]["000a-hello-world"]
        self.assertEqual([row["user"] for row in rows], ["b", "a"])
        self.assertEqual(board["updated_at"], "2026-01-02T00:00:00+00:00")

    def test_altered_or_truncated_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "completions.jsonl"
            append_completions([entry("a", 5.0, "s1"), entry("b", 4.0, "s2")], path)
            lines = path.read_text().splitlines()
            tampered = json.loads(lines[0])
            tampered["score"] = 999.0
            path.write_text(json.dumps(tampered) + "\n" + lines[1] + "\n")
            with self.assertRaises(LedgerError):
                read_events(path)
            path.write_text(lines[1] + "\n")
            with self.assertRaises(LedgerError):
                read_events(path)

    def test_merge_seeds_ledger_from_existing_leaderboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            board_path = Path(tmp) / "leaderboard.json"
            old = entry("legacy", 9.0, None)
            board_path.write_text(json.dumps({"problems": {old["problem_id"]: [old]}}))
            board = merge_scoreboard_entries([entry("new", 1.0, "s1")], board_path)
            users = [row["user"] for row in board["problems"]["000a-hello-world"]]
            events = read_events(Path(tmp) / "completions.jsonl")
        self.assertEqual(users, ["new", "legacy"])
        self.assertEqual([e["verifier"] for e in events], ["legacy", "local"])


if __name__ == "__main__":
    unittest.main()
