#!/usr/bin/env python
"""Rebuild demo students for the teacher dashboard.

- Xóa toàn bộ học viên mock cũ + dữ liệu học tập của họ (chỉ dữ liệu demo).
- Tạo lại 30 học viên với TÊN TIẾNG VIỆT HỢP LÝ, KHÔNG TRÙNG.
- Mỗi học viên đăng ký 3-4 môn (qua lớp A/B đã có của teacher id=2),
  làm bài thi (baseline/chapter/final), có điểm tài liệu, learner profile,
  learning progress → dashboard giảng viên trông đẹp nhất.

Chạy từ project root:  python rebuild_demo_students.py
An toàn chạy lại (idempotent): mỗi lần chạy sẽ dọn sạch và tạo lại.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sqlite3  # noqa: E402

from db.database import SessionLocal  # noqa: E402
from db import models  # noqa: E402
from api.auth import hash_password  # noqa: E402

DB_PATH = ROOT_DIR / "test.db"

NUM_STUDENTS = 30
DEFAULT_PASSWORD = "NovaStudent@123"

# 30 tên tiếng Việt hợp lý, không trùng (họ + tên đệm + tên).
STUDENT_NAMES = [
    "Nguyễn Văn An", "Trần Đức Bình", "Lê Hoàng Cường", "Phạm Minh Dũng",
    "Vũ Thị Hoa", "Đặng Quang Huy", "Bùi Thị Lan", "Hoàng Văn Long",
    "Phan Thị Mai", "Đỗ Thành Nam", "Ngô Thị Phương", "Dương Văn Quân",
    "Lý Thị Quỳnh", "Mai Văn Sơn", "Đinh Thị Thảo", "Trịnh Văn Trung",
    "Phùng Thị Thu", "Tô Văn Tuấn", "Cao Thị Vân", "Hồ Văn Việt",
    "Chu Thị Xuân", "Hà Văn Yến", "Lương Thị Zừng", "Kiều Văn Anh",
    "Tống Thị Bích", "Tăng Văn Cương", "La Thị Diệu", "Đoàn Văn Giang",
    "Cát Thị Hồng", "Sâm Văn Khánh",
]

# Môn học đã seed (tên → subject_id). Lấy động từ DB.
SEED_SUBJECT_NAMES = [
    "Cơ sở Hệ điều hành",
    "Vi xử lý",
    "Cơ sở dữ liệu",
    "Mạng máy tính",
]


def get_seed_classrooms_by_subject(db) -> dict:
    """Trả {subject_id: [classroom_A, classroom_B]} cho các môn seed của teacher 2."""
    result: dict[int, list] = {}
    classrooms = (
        db.query(models.Classroom)
        .filter(models.Classroom.name.like("% - Lớp _"))
        .order_by(models.Classroom.id.asc())
        .all()
    )
    for c in classrooms:
        result.setdefault(c.subject_id, []).append(c)
    return result


def get_documents_by_subject(db, subject_id: int):
    return (
        db.query(models.Document)
        .filter(models.Document.subject_id == subject_id)
        .order_by(models.Document.id.asc())
        .all()
    )


def delete_all_demo_students(db):
    """Xóa toàn bộ học viên + dữ liệu học tập liên quan (chỉ demo, an toàn chạy lại)."""
    rows = db.query(models.User).filter(models.User.role == "student").all()
    student_ids = [u.id for u in rows]

    if student_ids:
        placeholders = ",".join(["?"] * len(student_ids))
        con = db.connection().connection  # raw sqlite để xóa nhanh theo batch
        # Bảng con chứa user_id phải xóa trước khi xóa user.
        for table in [
            "wrong_answer_records",
            "student_learning_plan_steps",
            "student_learning_plans",
            "student_document_score_history",
            "student_document_evaluations",
            "assessment_results",
            "assessment_history",
            "learner_profiles",
            "student_learning_progress",
            "study_sessions",
            "learning_roadmaps",
            "orbit_chat_messages",
            "orbit_chat_sessions",
            "orbit_weekly_reminder_logs",
            "user_login_sessions",
            "enrollments",
        ]:
            try:
                con.execute(f"DELETE FROM {table} WHERE user_id IN ({placeholders})", student_ids)
            except sqlite3.OperationalError:
                # Bảng có thể không tồn tại hoặc không có user_id → bỏ qua.
                pass
        # orbit_coach_directives dùng student_id, không phải user_id.
        try:
            con.execute(
                f"DELETE FROM orbit_coach_directives WHERE student_id IN ({placeholders})",
                student_ids,
            )
        except sqlite3.OperationalError:
            pass
        # notifications dùng actor_user_id / recipient_user_id.
        try:
            con.execute(
                f"DELETE FROM notifications WHERE actor_user_id IN ({placeholders}) "
                f"OR recipient_user_id IN ({placeholders})",
                student_ids + student_ids,
            )
        except sqlite3.OperationalError:
            pass
        con.commit()

    for u in rows:
        db.delete(u)
    db.commit()
    return len(rows)


def score_for(student_idx: int, subject_idx: int, phase: str) -> float:
    """Điểm phân bổ đẹp: yếu → khá giỏi, xác định theo idx."""
    base = 40 + ((student_idx * 7 + subject_idx * 11) % 52)
    if phase == "baseline":
        return float(max(20, min(90, base - 12)))
    if phase == "chapter":
        return float(max(28, min(95, base - 3 + (student_idx % 3))))
    return float(max(35, min(98, base + 6 + (subject_idx % 4))))


def assign_subject_indexes(student_idx: int) -> list[int]:
    """Mỗi học viên tham gia 3 môn (thiếu 1 môn luân phiên để cân bằng)."""
    miss = (student_idx - 1) % 4
    return [i for i in range(4) if i != miss]


def main():
    db = SessionLocal()
    try:
        # Lấy môn + lớp seed.
        subjects = []
        for name in SEED_SUBJECT_NAMES:
            s = db.query(models.Subject).filter(models.Subject.name == name).first()
            if s:
                subjects.append(s)
        if len(subjects) != 4:
            print(f"[warn] Tìm thấy {len(subjects)} môn seed (cần 4). Tạo vẫn tiếp tục với số môn có.")

        classrooms_by_subject = get_seed_classrooms_by_subject(db)
        docs_by_subject = {s.id: get_documents_by_subject(db, s.id) for s in subjects}

        # 1) Dọn sạch học viên cũ.
        deleted = delete_all_demo_students(db)
        print(f"Đã xóa {deleted} học viên cũ (+ dữ liệu học tập).")

        # 2) Tạo học viên mới với tên Việt hợp lý.
        now = datetime.utcnow()
        created = 0
        for idx, name in enumerate(STUDENT_NAMES[:NUM_STUDENTS], start=1):
            student = models.User(
                username=f"nova_student_{idx:02d}",
                hashed_password=hash_password(DEFAULT_PASSWORD),
                role="student",
                full_name=name,
                student_id=f"SV{202600 + idx:04d}",
            )
            db.add(student)
            db.flush()
            created += 1

            subject_indexes = assign_subject_indexes(idx)
            for s_idx in subject_indexes:
                if s_idx >= len(subjects):
                    continue
                subject = subjects[s_idx]
                classes = classrooms_by_subject.get(subject.id, [])
                if not classes:
                    continue
                # Xen kẽ lớp A/B để cân bằng.
                classroom = classes[(idx + s_idx) % len(classes)]
                if student not in classroom.students:
                    classroom.students.append(student)

                # Assessment 3 pha (baseline/chapter/final).
                for phase, days_ago, total_q in [
                    ("baseline", 14, 10),
                    ("chapter", 7, 15),
                    ("final", 1, 20),
                ]:
                    score = score_for(idx, s_idx, phase)
                    correct = max(0, min(total_q, round((score / 100.0) * total_q)))
                    db.add(
                        models.AssessmentHistory(
                            user_id=student.id,
                            subject_id=subject.id,
                            subject=subject.name,
                            score=score,
                            test_type=phase,
                            total_questions=total_q,
                            correct_count=correct,
                            wrong_detail=f"rebuild_demo:{phase}",
                            level_at_time=("Beginner" if score < 50 else "Intermediate" if score < 80 else "Advanced"),
                            timestamp=now - timedelta(days=days_ago),
                            duration_seconds=600 + (idx * 23) + (s_idx * 17) + (total_q - correct) * 30,
                        )
                    )

                # Điểm tài liệu (2-3 tài liệu đầu mỗi môn).
                docs = docs_by_subject.get(subject.id, [])
                n_docs = 2 if idx % 2 == 0 else 3
                for d_idx, doc in enumerate(docs[:n_docs]):
                    base = score_for(idx, s_idx, "final")
                    doc_score = float(max(18, min(99, base + (d_idx * 5) - ((idx % 3) * 4))))
                    total_q = 15
                    correct = max(0, min(total_q, round((doc_score / 100.0) * total_q)))
                    db.add(
                        models.StudentDocumentEvaluation(
                            user_id=student.id,
                            document_id=doc.id,
                            subject_id=subject.id,
                            class_id=classroom.id,
                            latest_score=doc_score,
                            attempts=1 + (d_idx % 2),
                            is_completed=bool(doc_score >= 60),
                            last_test_at=now - timedelta(days=d_idx + 1),
                        )
                    )
                    db.add(
                        models.StudentDocumentScoreHistory(
                            user_id=student.id,
                            document_id=doc.id,
                            subject_id=subject.id,
                            class_id=classroom.id,
                            score=doc_score,
                            test_type=f"rebuild_demo:doc{d_idx}",
                            total_questions=total_q,
                            correct_count=correct,
                            tested_at=now - timedelta(days=d_idx + 1),
                        )
                    )

                # Learner profile.
                final = score_for(idx, s_idx, "final")
                level = "Beginner" if final < 50 else "Intermediate" if final < 80 else "Advanced"
                db.add(
                    models.LearnerProfile(
                        user_id=student.id,
                        subject_id=subject.id,
                        subject=subject.name,
                        current_level=level,
                        total_tests=3,
                        avg_score=final,
                    )
                )

            # Learning progress tổng.
            db.add(
                models.StudentLearningProgress(
                    user_id=student.id,
                    lessons_completed_total=(idx % 6) + 2,
                    tests_completed_total=(idx % 4) + 2,
                    total_study_minutes=120 + (idx * 9),
                    total_agent_messages=(idx % 5) + 1,
                    total_agent_chat_seconds=idx * 60,
                    last_active_at=now - timedelta(hours=idx % 48),
                    last_login_at=now - timedelta(hours=idx % 48),
                )
            )

        db.commit()

        # Tổng kết.
        total_enroll = len(db.execute(models.enrollment_table.select()).fetchall())
        total_assess = db.query(models.AssessmentHistory).count()
        total_eval = db.query(models.StudentDocumentEvaluation).count()
        print(f"Đã tạo {created} học viên mới.")
        print(f"  đăng ký (enrollments): {total_enroll}")
        print(f"  bài làm (assessment_history): {total_assess}")
        print(f"  điểm tài liệu (student_document_evaluations): {total_eval}")
        print("Mật độ lớp:")
        for s in subjects:
            for c in classrooms_by_subject.get(s.id, []):
                print(f"  - {c.name}: {len(c.students)} học viên")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
