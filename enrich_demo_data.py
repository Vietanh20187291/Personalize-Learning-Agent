#!/usr/bin/env python
"""Enrich demo data so the teacher dashboard shows students + scores.

- Khôi phục lại account test "ABX" (nguyenvanc@gmail.com, MSSV 122222) với hash cũ.
- Đăng ký ABX + các sinh viên hiện có vào 8 lớp CÓ TÀI LIỆU (nơi GV xem điểm).
- Bồi điểm tài liệu (StudentDocumentEvaluation) cho từng sinh viên theo tài liệu thật
  trong từng lớp → GV thấy điểm trong dashboard.
- Bồi AssessmentHistory (baseline/chapter/final) theo môn để có biểu đồ điểm.

Chạy từ project root:  python enrich_demo_data.py
Idempotent: chạy lại không trùng lặp (upsert theo user+document / user+subject+phase).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db.database import SessionLocal  # noqa: E402
from db import models  # noqa: E402

# Lớp CÓ tài liệu (GV sẽ xem điểm ở đây): class_id -> (subject_id, subject_name).
TARGET_CLASS_IDS = [1, 18, 19, 20, 21, 22, 23, 24]

# Account ABX gốc cần khôi phục (hash lấy từ backup).
ABX_USER = {
    "id": 4,
    "username": "nguyenvanc@gmail.com",
    "full_name": "ABX",
    "student_id": "122222",
    "hashed_password": (
        "$argon2id$v=19$m=65536,t=3,p=4$p/Q+J+Rci1EKwTgnZIyR8g$"
        "kgqVoZag7CcBVl2THlik27sv+MXsuNtFp0gjNEAdkp8"
    ),
}


def get_target_classes(db):
    rows = db.query(models.Classroom).filter(models.Classroom.id.in_(TARGET_CLASS_IDS)).all()
    # Sắp theo id để ổn định.
    return sorted(rows, key=lambda c: c.id)


def get_documents_for_class(db, classroom):
    return (
        db.query(models.Document)
        .filter(models.Document.class_id == classroom.id)
        .order_by(models.Document.id.asc())
        .all()
    )


def restore_abx(db):
    """Khôi phục account ABX (id=4) nếu chưa có."""
    user = db.query(models.User).filter(models.User.username == ABX_USER["username"]).first()
    if user is None:
        user = models.User(
            id=ABX_USER["id"],
            username=ABX_USER["username"],
            full_name=ABX_USER["full_name"],
            student_id=ABX_USER["student_id"],
            role="student",
            hashed_password=ABX_USER["hashed_password"],
        )
        db.add(user)
        db.flush()
        print(f"Đã khôi phục ABX: id={user.id} username={user.username} (MSSV {user.student_id})")
    else:
        # Đảm bảo thông tin đúng.
        user.full_name = ABX_USER["full_name"]
        user.student_id = ABX_USER["student_id"]
        user.hashed_password = ABX_USER["hashed_password"]
        print(f"ABX đã tồn tại: id={user.id} username={user.username}")
    return user


def ensure_enrollment(db, student, classroom):
    if student not in classroom.students:
        classroom.students.append(student)


def score_for(student_idx: int, subject_idx: int, phase: str) -> float:
    """Điểm phân bổ đẹp: yếu → giỏi, xác định theo idx."""
    base = 42 + ((student_idx * 7 + subject_idx * 11) % 50)
    if phase == "baseline":
        return float(max(22, min(90, base - 12)))
    if phase == "chapter":
        return float(max(30, min(95, base - 3 + (student_idx % 3))))
    return float(max(38, min(98, base + 6 + (subject_idx % 4))))


def upsert_assessment(db, student, subject, classroom, student_idx, subject_idx, phase, days_ago, total_q):
    marker = f"enrich_demo:{phase}"
    exists = (
        db.query(models.AssessmentHistory)
        .filter(
            models.AssessmentHistory.user_id == student.id,
            models.AssessmentHistory.subject_id == subject.id,
            models.AssessmentHistory.test_type == phase,
            models.AssessmentHistory.wrong_detail == marker,
        )
        .first()
    )
    if exists:
        return
    score = score_for(student_idx, subject_idx, phase)
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
            wrong_detail=marker,
            level_at_time=("Beginner" if score < 50 else "Intermediate" if score < 80 else "Advanced"),
            timestamp=datetime.utcnow() - timedelta(days=days_ago),
            duration_seconds=600 + (student_idx * 23) + (subject_idx * 17) + (total_q - correct) * 30,
        )
    )


def upsert_doc_eval(db, student, doc, subject, classroom, student_idx, doc_idx):
    base = score_for(student_idx, 0, "final")
    doc_score = float(max(18, min(99, base + (doc_idx * 5) - ((student_idx % 3) * 4))))
    eval_row = (
        db.query(models.StudentDocumentEvaluation)
        .filter(
            models.StudentDocumentEvaluation.user_id == student.id,
            models.StudentDocumentEvaluation.document_id == doc.id,
        )
        .first()
    )
    if eval_row:
        # Chỉ cập nhật nếu rỗng để không đè dữ liệu thật người dùng đã tạo.
        return
    total_q = 15
    correct = max(0, min(total_q, round((doc_score / 100.0) * total_q)))
    db.add(
        models.StudentDocumentEvaluation(
            user_id=student.id,
            document_id=doc.id,
            subject_id=subject.id,
            class_id=classroom.id,
            latest_score=doc_score,
            attempts=1 + (doc_idx % 2),
            is_completed=bool(doc_score >= 60),
            last_test_at=datetime.utcnow() - timedelta(days=doc_idx + 1),
        )
    )
    # Score history.
    hist_marker = f"enrich_demo:doc{doc_idx}"
    hist_exists = (
        db.query(models.StudentDocumentScoreHistory)
        .filter(
            models.StudentDocumentScoreHistory.user_id == student.id,
            models.StudentDocumentScoreHistory.document_id == doc.id,
            models.StudentDocumentScoreHistory.test_type == hist_marker,
        )
        .first()
    )
    if not hist_exists:
        db.add(
            models.StudentDocumentScoreHistory(
                user_id=student.id,
                document_id=doc.id,
                subject_id=subject.id,
                class_id=classroom.id,
                score=doc_score,
                test_type=hist_marker,
                total_questions=total_q,
                correct_count=correct,
                tested_at=datetime.utcnow() - timedelta(days=doc_idx + 1),
            )
        )


def main():
    db = SessionLocal()
    try:
        # 1) Khôi phục ABX.
        abx = restore_abx(db)

        # 2) Lấy danh sách sinh viên (ABX + 30 sinh viên seed).
        students = (
            db.query(models.User)
            .filter(models.User.role == "student")
            .order_by(models.User.id.asc())
            .all()
        )
        print(f"Tổng sinh viên (gồm ABX): {len(students)}")

        target_classes = get_target_classes(db)
        print(f"Lớp mục tiêu (có tài liệu): {[(c.id, c.name) for c in target_classes]}")

        # 3) Đăng ký + bồi dữ liệu.
        now = datetime.utcnow()
        for s_idx, student in enumerate(students):
            for c_idx, classroom in enumerate(target_classes):
                subject = classroom.subject_obj or (
                    db.query(models.Subject).filter(models.Subject.id == classroom.subject_id).first()
                )
                if subject is None:
                    continue
                ensure_enrollment(db, student, classroom)

                docs = get_documents_for_class(db, classroom)
                for d_idx, doc in enumerate(docs):
                    upsert_doc_eval(db, student, doc, subject, classroom, s_idx, d_idx)

                # Assessment 3 pha theo môn (chỉ 1 lần/môn/SV).
                for phase, days_ago, total_q in [("baseline", 14, 10), ("chapter", 7, 15), ("final", 1, 20)]:
                    upsert_assessment(db, student, subject, classroom, s_idx, c_idx, phase, days_ago, total_q)

        db.commit()

        # 4) Tổng kết.
        enroll_now = len(db.execute(models.enrollment_table.select()).fetchall())
        assess_now = db.query(models.AssessmentHistory).count()
        eval_now = db.query(models.StudentDocumentEvaluation).count()
        print("─" * 40)
        print(f"Đăng ký (enrollments): {enroll_now}")
        print(f"Bài kiểm tra (assessment_history): {assess_now}")
        print(f"Điểm tài liệu (student_document_evaluations): {eval_now}")
        print("Mật độ lớp mục tiêu:")
        for c in target_classes:
            print(f"  - {c.name}: {len(c.students)} học viên")
        print()
        print("ABX tham gia lớp:")
        abx_fresh = db.query(models.User).filter(models.User.username == ABX_USER["username"]).first()
        if abx_fresh:
            for c in abx_fresh.enrolled_classes:
                print(f"  - {c.name}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
