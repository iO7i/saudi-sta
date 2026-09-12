from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any


class Store:
    """Small local SQLite store. Browser clients never submit filesystem paths."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.audio_dir = self.data_dir / "audio"
        self.exports_dir = self.data_dir / "exports"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(exist_ok=True)
        self.exports_dir.mkdir(exist_ok=True)
        try:
            os.chmod(self.data_dir, 0o700)
            os.chmod(self.audio_dir, 0o700)
        except OSError:
            # Windows ACLs remain the controlling access mechanism.
            pass
        self.db_path = self.data_dir / "saudi_sta.sqlite3"
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS recipes (
                  id TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS records (
                  id TEXT PRIMARY KEY, original_text TEXT NOT NULL, text TEXT NOT NULL, revision INTEGER NOT NULL,
                  recording_name TEXT, outputs TEXT NOT NULL, permissions TEXT NOT NULL, label_state TEXT NOT NULL,
                  review TEXT NOT NULL, review_state TEXT NOT NULL DEFAULT 'RECORDED', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS sandbox (
                  id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tournaments (
                  id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS recordings (
                  id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime_type TEXT NOT NULL, bytes INTEGER NOT NULL,
                  duration_seconds REAL, audio_sha256 TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS seed_human_cases (
                  id TEXT PRIMARY KEY, recording_id TEXT NOT NULL UNIQUE, reviewed_transcript TEXT NOT NULL,
                  expected TEXT NOT NULL, provenance TEXT NOT NULL, review_state TEXT NOT NULL DEFAULT 'HUMAN_TRANSCRIPT_REVIEWED',
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            record_columns = {row[1] for row in conn.execute("PRAGMA table_info(records)").fetchall()}
            if "review_state" not in record_columns:
                conn.execute("ALTER TABLE records ADD COLUMN review_state TEXT NOT NULL DEFAULT 'RECORDED'")
            seed_columns = {row[1] for row in conn.execute("PRAGMA table_info(seed_human_cases)").fetchall()}
            if "review_state" not in seed_columns:
                conn.execute("ALTER TABLE seed_human_cases ADD COLUMN review_state TEXT NOT NULL DEFAULT 'HUMAN_TRANSCRIPT_REVIEWED'")
            recording_columns = {row[1] for row in conn.execute("PRAGMA table_info(recordings)").fetchall()}
            if "audio_sha256" not in recording_columns:
                conn.execute("ALTER TABLE recordings ADD COLUMN audio_sha256 TEXT")
            conn.execute(
                "INSERT OR IGNORE INTO sandbox(id, body) VALUES(1, ?)",
                (json.dumps({"notes": [], "reminders": [], "lists": {}, "applied_proposal_ids": []}),),
            )

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def save_recipe(self, recipe: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO recipes(id, body) VALUES(?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body, updated_at=CURRENT_TIMESTAMP",
                (recipe["id"], self._dump(recipe)),
            )

    def get_recipe(self, recipe_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT body FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        return json.loads(row["body"]) if row else None

    def list_recipes(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT body FROM recipes ORDER BY updated_at, id").fetchall()
        return [json.loads(row["body"]) for row in rows]

    def save_record(
        self,
        text: str,
        outputs: dict[str, Any],
        recording_name: str | None = None,
        *,
        original_text: str | None = None,
    ) -> str:
        record_id = str(uuid.uuid4())
        permissions = {
            "processing": "granted",
            "retention": "unknown",
            "third_party_processing": "denied",
            "training_use": "unknown",
            "public_redistribution": "denied",
            "provider_output_training_terms": "unknown",
        }
        review = {"reviewer_type": "unknown", "reviewer_identity": None, "promotion_reason": None}
        review_state = "MODEL_TRANSCRIBED" if outputs.get("transcription") else "RECORDED"
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO records(id, original_text, text, revision, recording_name, outputs, permissions, label_state, review, review_state)
                VALUES (?, ?, ?, 1, ?, ?, ?, 'CANDIDATE', ?, ?)""",
                (record_id, original_text if original_text is not None else text, text, recording_name,
                 self._dump(outputs), self._dump(permissions), self._dump(review), review_state),
            )
        return record_id

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        return self._record(row) if row else None

    def list_records(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM records ORDER BY created_at DESC LIMIT 100").fetchall()
        return [self._record(row) for row in rows]

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, Any]:
        output = dict(row)
        for key in ("outputs", "permissions", "review"):
            output[key] = json.loads(output[key])
        return output

    def edit_transcript(self, record_id: str, text: str, expected_revision: int) -> dict[str, Any] | None:
        record = self.get_record(record_id)
        if not record:
            return None
        if record["revision"] != expected_revision:
            raise ValueError("REVISION_CONFLICT")
        outputs = record["outputs"]
        edits = outputs.setdefault("transcript_edit_history", [])
        edits.append({"from_revision": expected_revision, "original_text": record["text"], "edited_text": text})
        outputs["stale"] = True
        outputs["stale_reason"] = "Transcript was edited; summary, plan, and proposal refer to an older source revision."
        with self._connect() as conn:
            conn.execute(
                "UPDATE records SET text=?, revision=revision+1, outputs=? WHERE id=? AND revision=?",
                (text, self._dump(outputs), record_id, expected_revision),
            )
        return self.get_record(record_id)

    def update_record_outputs(self, record_id: str, outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Persist append-only route/apply evidence without changing the transcript revision."""
        with self._connect() as conn:
            result = conn.execute("UPDATE records SET outputs=? WHERE id=?", (self._dump(outputs), record_id))
        return self.get_record(record_id) if result.rowcount else None

    def update_review(self, record_id: str, review: dict[str, Any], label_state: str) -> dict[str, Any] | None:
        current = self.get_record(record_id)
        if not current:
            return None
        review_state = current.get("review_state", "RECORDED")
        if review.get("reviewer_type") == "human":
            review_state = "HUMAN_TRANSCRIPT_REVIEWED"
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE records SET review=?, label_state=?, review_state=? WHERE id=?",
                (self._dump(review), label_state, review_state, record_id),
            )
        return self.get_record(record_id) if result.rowcount else None

    def set_review_state(self, record_id: str, review_state: str) -> dict[str, Any] | None:
        if review_state not in {"RECORDED", "MODEL_TRANSCRIBED", "HUMAN_TRANSCRIPT_REVIEWED", "SEMANTIC_REFERENCE_REVIEWED"}:
            raise ValueError("INVALID_REVIEW_STATE")
        with self._connect() as conn:
            result = conn.execute("UPDATE records SET review_state=? WHERE id=?", (review_state, record_id))
        return self.get_record(record_id) if result.rowcount else None

    def delete_record(self, record_id: str) -> bool:
        record = self.get_record(record_id)
        if not record:
            return False
        filename = record.get("recording_name")
        with self._connect() as conn:
            conn.execute("DELETE FROM records WHERE id=?", (record_id,))
        if filename and Path(filename).name == filename:
            target = self.audio_dir / filename
            with self._connect() as conn:
                conn.execute("DELETE FROM recordings WHERE filename=?", (filename,))
            if target.exists() and target.resolve().parent == self.audio_dir.resolve():
                target.unlink()
        return True

    def get_sandbox(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT body FROM sandbox WHERE id=1").fetchone()
        return json.loads(row["body"])

    def save_sandbox(self, state: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sandbox SET body=? WHERE id=1", (self._dump(state),))

    def apply_sandbox_once(self, proposal: Any, applier: Any) -> tuple[dict[str, Any], str]:
        """Apply a proposal under a write lock so repeated Apply is idempotent."""
        proposal_id = str(getattr(proposal, "id", ""))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT body FROM sandbox WHERE id=1").fetchone()
            state = json.loads(row["body"]) if row else {"notes": [], "reminders": [], "lists": {}, "applied_proposal_ids": []}
            if proposal_id in state.setdefault("applied_proposal_ids", []):
                conn.commit()
                return state, "ALREADY_APPLIED"
            updated, status = applier(state, proposal)
            conn.execute("UPDATE sandbox SET body=? WHERE id=1", (self._dump(updated),))
            conn.commit()
            return updated, status

    def save_tournament(self, report: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO tournaments(id, body) VALUES(?, ?)", (report["id"], self._dump(report)))

    def get_tournament(self, tournament_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT body FROM tournaments WHERE id=?", (tournament_id,)).fetchone()
        return json.loads(row["body"]) if row else None

    def save_audio(self, payload: bytes, suffix: str, mime_type: str, duration_seconds: float | None) -> tuple[str, str]:
        recording_id = str(uuid.uuid4())
        filename = f"{recording_id}{suffix}"
        target = self.audio_dir / filename
        target.write_bytes(payload)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        audio_sha256 = hashlib.sha256(payload).hexdigest()
        with self._connect() as conn:
            conn.execute("INSERT INTO recordings(id, filename, mime_type, bytes, duration_seconds, audio_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                         (recording_id, filename, mime_type, len(payload), duration_seconds, audio_sha256))
        return recording_id, filename

    def audio_path(self, filename: str) -> Path | None:
        if Path(filename).name != filename:
            return None
        target = self.audio_dir / filename
        if not target.exists() or target.resolve().parent != self.audio_dir.resolve():
            return None
        return target

    def recording(self, recording_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)).fetchone()
        return dict(row) if row else None

    def recording_path(self, recording_id: str) -> Path | None:
        recording = self.recording(recording_id)
        return self.audio_path(recording["filename"]) if recording else None

    def save_seed_human_case(self, recording_id: str, reviewed_transcript: str, expected: dict[str, Any], provenance: dict[str, Any], review_state: str = "HUMAN_TRANSCRIPT_REVIEWED") -> dict[str, Any]:
        case_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO seed_human_cases(id, recording_id, reviewed_transcript, expected, provenance, review_state) VALUES (?, ?, ?, ?, ?, ?)",
                (case_id, recording_id, reviewed_transcript, self._dump(expected), self._dump(provenance), review_state),
            )
        return self.get_seed_human_case(case_id)  # type: ignore[return-value]

    @staticmethod
    def _seed_case(row: sqlite3.Row) -> dict[str, Any]:
        body = dict(row)
        body["expected"] = json.loads(body["expected"])
        body["provenance"] = json.loads(body["provenance"])
        body["evidence_type"] = "HUMAN_REVIEWED"
        body["dataset_id"] = "SEED_HUMAN_EVAL"
        body.setdefault("review_state", "HUMAN_TRANSCRIPT_REVIEWED")
        return body

    def get_seed_human_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM seed_human_cases WHERE id=?", (case_id,)).fetchone()
        return self._seed_case(row) if row else None

    def list_seed_human_cases(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM seed_human_cases ORDER BY created_at, id").fetchall()
        return [self._seed_case(row) for row in rows]

    def training_manifest(self) -> dict[str, Any]:
        eligible, excluded = [], []
        for record in self.list_records():
            reasons = []
            permissions = record["permissions"]
            if permissions["training_use"] != "granted":
                reasons.append("training_use_not_granted")
            if permissions["public_redistribution"] != "granted":
                reasons.append("public_redistribution_not_granted")
            if permissions["provider_output_training_terms"] != "granted":
                reasons.append("provider_output_terms_unknown_or_denied")
            if record["label_state"] not in {"SILVER", "GOLD"}:
                reasons.append("label_not_training_ready")
            entry = {"record_id": record["id"], "label_state": record["label_state"], "reasons": reasons}
            (excluded if reasons else eligible).append(entry)
        return {
            "format": "SAUDI_STA_TRAINING_MANIFEST_V1",
            "private_audio_included": False,
            "eligible": eligible,
            "excluded": excluded,
            "automatic_silver_promotion": False,
        }
