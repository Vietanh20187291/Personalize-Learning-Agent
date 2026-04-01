import sqlite3
from pathlib import Path

DB_PATH = Path(r"c:\Users\DELL\Desktop\2023\LVTN\New\ai-personalized-learning-Test1\test.db")


def table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cur.fetchone() is not None


def has_column(cur, table_name: str, column_name: str) -> bool:
    cur.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cur.fetchall())


def ensure_subjects_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY,
            name VARCHAR UNIQUE,
            description VARCHAR,
            icon VARCHAR,
            created_at DATETIME
        )
        """
    )


def ensure_column(cur, table: str, col_def: str):
    col_name = col_def.split()[0]
    if table_exists(cur, table) and not has_column(cur, table, col_name):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        print(f"Added column {table}.{col_name}")


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    ensure_subjects_table(cur)

    for table in [
        "classrooms",
        "documents",
        "learning_roadmaps",
        "learner_profiles",
        "study_sessions",
        "assessment_history",
        "question_bank",
        "chunks",
        "assessment_results",
    ]:
        ensure_column(cur, table, "subject_id INTEGER")

    if table_exists(cur, "classrooms"):
        cur.execute("SELECT DISTINCT subject FROM classrooms WHERE subject IS NOT NULL AND TRIM(subject) != ''")
        subject_names = [row[0].strip() for row in cur.fetchall()]

        for name in subject_names:
            cur.execute("INSERT OR IGNORE INTO subjects(name, description) VALUES(?, ?)", (name, f"Môn {name}"))

        cur.execute(
            """
            UPDATE classrooms
            SET subject_id = (
                SELECT s.id FROM subjects s WHERE lower(s.name) = lower(classrooms.subject)
            )
            WHERE subject_id IS NULL
            """
        )

    if table_exists(cur, "documents") and has_column(cur, "documents", "class_id"):
        cur.execute(
            """
            UPDATE documents
            SET subject_id = (
                SELECT c.subject_id FROM classrooms c WHERE c.id = documents.class_id
            )
            WHERE subject_id IS NULL
            """
        )

    conn.commit()

    if table_exists(cur, "classrooms"):
        cur.execute("SELECT COUNT(*) FROM classrooms WHERE subject_id IS NULL")
        missing = cur.fetchone()[0]
        print(f"Classrooms missing subject_id: {missing}")

    print("Migration done")
    conn.close()


if __name__ == "__main__":
    main()
