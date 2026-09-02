from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "instance" / "sunjudge.sqlite"
HEAD_REVISION = "7c91a2b4e8d0"


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    create_m3_tables(cur)
    add_column(cur, "assignments", "submission_requirements_json JSON")
    add_column(cur, "submissions", "submission_item_key VARCHAR(80)")
    add_column(cur, "submissions", "submission_item_label VARCHAR(120)")
    backfill_submission_requirements(cur)
    cur.execute("UPDATE submissions SET submission_item_key = 'main' WHERE submission_item_key IS NULL OR submission_item_key = ''")
    cur.execute("UPDATE submissions SET submission_item_label = '提交文件' WHERE submission_item_label IS NULL OR submission_item_label = ''")
    create_assignment_grades(cur)
    create_assignment_reads(cur)
    cur.execute("UPDATE alembic_version SET version_num = ?", (HEAD_REVISION,))
    con.commit()
    print(f"migrated {DB_PATH} to {HEAD_REVISION}")


def create_m3_tables(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS teacher_llm_configs (
            id INTEGER NOT NULL PRIMARY KEY,
            teacher_id INTEGER NOT NULL UNIQUE,
            provider VARCHAR(40) NOT NULL,
            base_url VARCHAR(255) NOT NULL,
            model VARCHAR(120) NOT NULL,
            encrypted_api_key VARCHAR(500) NOT NULL,
            enabled BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY(teacher_id) REFERENCES users (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS judge_runs (
            id INTEGER NOT NULL PRIMARY KEY,
            submission_id INTEGER NOT NULL,
            status VARCHAR(40) NOT NULL,
            score FLOAT NOT NULL,
            details_json JSON NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY(submission_id) REFERENCES submissions (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS grading_results (
            id INTEGER NOT NULL PRIMARY KEY,
            submission_id INTEGER NOT NULL UNIQUE,
            auto_score FLOAT,
            llm_score FLOAT,
            final_score FLOAT,
            feedback TEXT,
            teacher_comment TEXT,
            reviewed_by INTEGER,
            status VARCHAR(30) NOT NULL,
            llm_details_json JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY(reviewed_by) REFERENCES users (id),
            FOREIGN KEY(submission_id) REFERENCES submissions (id)
        )
        """
    )


def create_assignment_grades(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_grades (
            id INTEGER NOT NULL PRIMARY KEY,
            assignment_id INTEGER NOT NULL,
            student_user_id INTEGER NOT NULL,
            auto_score FLOAT,
            llm_score FLOAT,
            final_score FLOAT,
            feedback TEXT,
            teacher_comment TEXT,
            reviewed_by INTEGER,
            status VARCHAR(30) NOT NULL,
            llm_details_json JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY(assignment_id) REFERENCES assignments (id),
            FOREIGN KEY(reviewed_by) REFERENCES users (id),
            FOREIGN KEY(student_user_id) REFERENCES users (id),
            UNIQUE (assignment_id, student_user_id)
        )
        """
    )


def create_assignment_reads(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_reads (
            id INTEGER NOT NULL PRIMARY KEY,
            assignment_id INTEGER NOT NULL,
            student_user_id INTEGER NOT NULL,
            read_at DATETIME NOT NULL,
            FOREIGN KEY(assignment_id) REFERENCES assignments (id),
            FOREIGN KEY(student_user_id) REFERENCES users (id),
            UNIQUE (assignment_id, student_user_id)
        )
        """
    )


def add_column(cur: sqlite3.Cursor, table_name: str, ddl: str) -> None:
    column_name = ddl.split()[0]
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in existing:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def backfill_submission_requirements(cur: sqlite3.Cursor) -> None:
    rows = cur.execute("SELECT id, file_rules_json, submission_requirements_json FROM assignments").fetchall()
    for assignment_id, file_rules_raw, requirements_raw in rows:
        if requirements_raw:
            continue
        try:
            rules = json.loads(file_rules_raw or "{}")
        except json.JSONDecodeError:
            rules = {}
        requirement = {
            "key": "main",
            "label": "提交文件",
            "allowed_extensions": rules.get("allowed_extensions") or [".py", ".md", ".zip", ".jpg", ".png"],
            "max_size_mb": rules.get("max_size_mb") or 5,
            "filename_template": rules.get("filename_template") or "{student_id}_{assignment_code}{extension}",
            "required": True,
        }
        cur.execute(
            "UPDATE assignments SET submission_requirements_json = ? WHERE id = ?",
            (json.dumps([requirement], ensure_ascii=False), assignment_id),
        )


if __name__ == "__main__":
    main()
