#!/usr/bin/env python
"""Seed demo data for the platform.

Creates:
- 1 teacher (nova_test_teacher)
- 4 subjects, 8 classes (2 per subject)
- 4 sample documents per subject (so documents exist to score against)
- 30 students, each enrolled in 3-4 classes
- Rich scoring data so dashboards look good:
    * AssessmentHistory (baseline / chapter / final)
    * StudentDocumentEvaluation + StudentDocumentScoreHistory (per document)
    * LearnerProfile (level + avg score)
    * StudentLearningProgress (lessons, tests, study minutes)

Idempotent: reuses existing rows, skips already-seeded rows by a marker.
Re-run safely. Run from project root:  python seed_nova_test_data.py
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Dict, List

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db.database import SessionLocal
from db import models
from api.auth import hash_password

SEED_MARKER = "seed_nova_test_data_v2"
SUBJECTS = [
    "Cơ sở Hệ điều hành",
    "Vi xử lý",
    "Cơ sở dữ liệu",
    "Mạng máy tính",
]

CLASS_SUFFIXES = ["Lớp A", "Lớp B"]
NUM_STUDENTS = 30


def get_or_create_teacher(db):
    teacher = db.query(models.User).filter(models.User.role == "teacher").order_by(models.User.id.asc()).first()
    if teacher:
        return teacher

    teacher = models.User(
        username="nova_test_teacher",
        hashed_password=hash_password("NovaTest@123"),
        role="teacher",
        full_name="Nova Test Teacher",
        student_id=None,
    )
    db.add(teacher)
    db.flush()
    return teacher


def get_or_create_subject(db, name: str) -> models.Subject:
    subject = db.query(models.Subject).filter(models.Subject.name.ilike(name)).first()
    if subject:
        return subject

    subject = models.Subject(
        name=name,
        description=f"Môn kiểm thử cho Nova: {name}",
        icon="📘",
    )
    db.add(subject)
    db.flush()
    return subject


def get_or_create_classroom(db, subject: models.Subject, teacher: models.User, suffix: str) -> models.Classroom:
    class_name = f"{subject.name} - {suffix}"
    classroom = (
        db.query(models.Classroom)
        .filter(models.Classroom.subject_id == subject.id, models.Classroom.name == class_name)
        .first()
    )
    if classroom:
        return classroom

    class_code = f"TEST-{subject.id:02d}-{suffix.upper().replace(' ', '-')[:8]}"
    classroom = models.Classroom(
        name=class_name,
        subject_id=subject.id,
        subject=subject.name,
        class_code=class_code,
        teacher_id=teacher.id,
    )
    db.add(classroom)
    db.flush()
    return classroom


def get_or_create_documents(db, subject: models.Subject, teacher: models.User) -> List[models.Document]:
    """Create sample documents for a subject so we can record document-level scores."""
    titles = [
        f"{subject.name} - Chương 1",
        f"{subject.name} - Chương 2",
        f"{subject.name} - Chương 3",
        f"{subject.name} - Chương 4",
    ]
    docs: List[models.Document] = []
    for idx, title in enumerate(titles, start=1):
        filename = f"{subject.name.replace(' ', '_')}_chuong{idx}.pdf"
        doc = (
            db.query(models.Document)
            .filter(models.Document.subject_id == subject.id, models.Document.filename == filename)
            .first()
        )
        if not doc:
            doc = models.Document(
                title=title,
                filename=filename,
                file_path=f"uploads/{filename}",
                subject_id=subject.id,
                subject=subject.name,
                teacher_id=teacher.id,
                class_id=None,
            )
            db.add(doc)
            db.flush()
        docs.append(doc)
    return docs


def get_or_create_student(db, index: int) -> models.User:
    username = f"nova_student_{index:02d}"
    student = db.query(models.User).filter(models.User.username == username).first()
    if student:
        return student

    first_names = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Phan", "Vũ", "Đặng", "Bùi", "Đỗ"]
    last_names = ["Văn An", "Thị Bình", "Văn Cường", "Thị Dung", "Văn Đức", "Thị Hoa", "Văn Khôi", "Thị Lan", "Văn Minh", "Thị Ngọc"]
    full_name = f"{first_names[(index - 1) % len(first_names)]} {last_names[(index - 1) % len(last_names)]} {index:02d}"

    student = models.User(
        username=username,
        hashed_password=hash_password("NovaStudent@123"),
        role="student",
        full_name=full_name,
        student_id=f"NV{202600 + index:03d}",
    )
    db.add(student)
    db.flush()
    return student


def assign_target_classes() -> Dict[int, List[int]]:
    """Each student joins 3 or 4 subjects (balanced ~8 students/class)."""
    target = {}
    for student_idx in range(1, NUM_STUDENTS + 1):
        # Cyclically miss one subject so distribution stays balanced across 30 students.
        miss = (student_idx - 1) % 4  # student 1 misses subj 0, student 2 misses subj 1, ...
        target[student_idx] = [s for s in [0, 1, 2, 3] if s != miss]
    return target


def score_for(student_idx: int, subject_idx: int, phase: str) -> float:
    """Deterministic, spread scores 18..98 (weak → excellent)."""
    base = 38 + ((student_idx * 7 + subject_idx * 11) % 48)
    if phase == "baseline":
        return float(max(18, min(92, base - 10)))
    if phase == "chapter":
        return float(max(20, min(96, base - 2 + (student_idx % 3))))
    return float(max(25, min(98, base + 6 + (subject_idx % 4))))


def ensure_single_subject_enrollment(student: models.User, classroom: models.Classroom):
    for enrolled in list(student.enrolled_classes):
        if enrolled.subject_id == classroom.subject_id and enrolled.id != classroom.id:
            enrolled.students.remove(student)
    if student not in classroom.students:
        classroom.students.append(student)


def clear_seed_subject_enrollments(student: models.User, seed_subject_ids: set):
    for enrolled in list(student.enrolled_classes):
        if enrolled.subject_id in seed_subject_ids:
            enrolled.students.remove(student)


def create_assessment_rows(db, student: models.User, subject: models.Subject, student_idx: int, subject_idx: int):
    phases = [
        ("baseline", datetime.utcnow() - timedelta(days=14), 10),
        ("chapter", datetime.utcnow() - timedelta(days=7), 15),
        ("final", datetime.utcnow() - timedelta(days=1), 20),
    ]

    for phase, timestamp, total_questions in phases:
        marker = f"{SEED_MARKER}:{phase}"
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
            continue

        score = score_for(student_idx, subject_idx, phase)
        correct_count = max(0, min(total_questions, round((score / 100.0) * total_questions)))
        wrong_count = max(0, total_questions - correct_count)
        db.add(
            models.AssessmentHistory(
                user_id=student.id,
                subject_id=subject.id,
                subject=subject.name,
                score=score,
                test_type=phase,
                total_questions=total_questions,
                correct_count=correct_count,
                wrong_detail=marker,
                level_at_time="Beginner" if score < 50 else "Intermediate" if score < 80 else "Advanced",
                timestamp=timestamp,
                duration_seconds=900 + (student_idx * 37) + (subject_idx * 13) + wrong_count,
            )
        )


def create_document_scores(
    db,
    student: models.User,
    subject: models.Subject,
    docs: List[models.Document],
    student_idx: int,
    subject_idx: int,
):
    """Per-document evaluation + score history (feeds document-level dashboards)."""
    # Score the first 2-3 documents per subject (deterministic, varied).
    n_docs = 2 if (student_idx % 2 == 0) else 3
    for doc_idx, doc in enumerate(docs[:n_docs]):
        base = score_for(student_idx, subject_idx, "final")
        # Vary a little per document so they look realistic.
        doc_score = float(max(15, min(99, base + (doc_idx * 5) - ((student_idx % 3) * 4))))
        total_q = 15
        correct = max(0, min(total_q, round((doc_score / 100.0) * total_q)))

        eval_row = (
            db.query(models.StudentDocumentEvaluation)
            .filter(
                models.StudentDocumentEvaluation.user_id == student.id,
                models.StudentDocumentEvaluation.document_id == doc.id,
            )
            .first()
        )
        attempts = 1 + (doc_idx % 2)
        if eval_row:
            eval_row.latest_score = doc_score
            eval_row.attempts = attempts
            eval_row.is_completed = bool(doc_score >= 60)
            eval_row.last_test_at = datetime.utcnow() - timedelta(days=doc_idx + 1)
        else:
            db.add(
                models.StudentDocumentEvaluation(
                    user_id=student.id,
                    document_id=doc.id,
                    subject_id=subject.id,
                    class_id=None,
                    latest_score=doc_score,
                    attempts=attempts,
                    is_completed=bool(doc_score >= 60),
                    last_test_at=datetime.utcnow() - timedelta(days=doc_idx + 1),
                )
            )

        # Score history (one row per attempt) — avoid duplicates by marker in test_type suffix.
        hist_marker = f"{SEED_MARKER}:doc{doc_idx}"
        exists = (
            db.query(models.StudentDocumentScoreHistory)
            .filter(
                models.StudentDocumentScoreHistory.user_id == student.id,
                models.StudentDocumentScoreHistory.document_id == doc.id,
                models.StudentDocumentScoreHistory.test_type == hist_marker,
            )
            .first()
        )
        if not exists:
            db.add(
                models.StudentDocumentScoreHistory(
                    user_id=student.id,
                    document_id=doc.id,
                    subject_id=subject.id,
                    class_id=None,
                    score=doc_score,
                    test_type=hist_marker,
                    total_questions=total_q,
                    correct_count=correct,
                    tested_at=datetime.utcnow() - timedelta(days=doc_idx + 1),
                )
            )


def create_learner_profile(db, student: models.User, subject: models.Subject, final_score: float):
    profile = (
        db.query(models.LearnerProfile)
        .filter(models.LearnerProfile.user_id == student.id, models.LearnerProfile.subject_id == subject.id)
        .first()
    )
    level = "Beginner" if final_score < 50 else "Intermediate" if final_score < 80 else "Advanced"
    if profile:
        profile.avg_score = final_score
        profile.current_level = level
        profile.total_tests = (profile.total_tests or 0) + 1
    else:
        db.add(
            models.LearnerProfile(
                user_id=student.id,
                subject_id=subject.id,
                subject=subject.name,
                current_level=level,
                total_tests=3,
                avg_score=final_score,
            )
        )


def create_learning_progress(db, student: models.User, student_idx: int):
    progress = db.query(models.StudentLearningProgress).filter(models.StudentLearningProgress.user_id == student.id).first()
    # Deterministic, realistic-ish numbers.
    lessons = (student_idx % 6) + 2
    tests = (student_idx % 4) + 2
    minutes = 120 + (student_idx * 9)
    if progress:
        progress.lessons_completed_total = lessons
        progress.tests_completed_total = tests
        progress.total_study_minutes = minutes
        progress.last_active_at = datetime.utcnow() - timedelta(hours=student_idx % 48)
    else:
        db.add(
            models.StudentLearningProgress(
                user_id=student.id,
                lessons_completed_total=lessons,
                tests_completed_total=tests,
                total_study_minutes=minutes,
                total_agent_messages=(student_idx % 5) + 1,
                total_agent_chat_seconds=(student_idx * 60),
                last_active_at=datetime.utcnow() - timedelta(hours=student_idx % 48),
            )
        )


def main():
    db = SessionLocal()
    try:
        teacher = get_or_create_teacher(db)
        subjects = [get_or_create_subject(db, name) for name in SUBJECTS]
        classrooms = []
        subject_docs: Dict[int, List[models.Document]] = {}
        for subject in subjects:
            for suffix in CLASS_SUFFIXES:
                classrooms.append(get_or_create_classroom(db, subject, teacher, suffix))
            subject_docs[subject.id] = get_or_create_documents(db, subject, teacher)

        target_subject_indexes = assign_target_classes()
        students: List[models.User] = []
        seed_subject_ids = {subject.id for subject in subjects}

        for student_idx in range(1, NUM_STUDENTS + 1):
            student = get_or_create_student(db, student_idx)
            students.append(student)
            clear_seed_subject_enrollments(student, seed_subject_ids)

            for subject_idx in target_subject_indexes[student_idx]:
                subject = subjects[subject_idx]
                class_variant = "Lớp A" if (student_idx + subject_idx) % 2 == 0 else "Lớp B"
                classroom = next(
                    item for item in classrooms
                    if item.subject_id == subject.id and item.name == f"{subject.name} - {class_variant}"
                )
                ensure_single_subject_enrollment(student, classroom)
                create_assessment_rows(db, student, subject, student_idx, subject_idx)
                create_document_scores(db, student, subject, subject_docs[subject.id], student_idx, subject_idx)
                final_score = score_for(student_idx, subject_idx, "final")
                create_learner_profile(db, student, subject, final_score)

            create_learning_progress(db, student, student_idx)

        db.commit()

        print("Seed Nova test data completed (v2)")
        print(f"Teacher: {teacher.username} (id={teacher.id})")
        print(f"Subjects: {len(subjects)} | Classes: {len(classrooms)} | Documents: {sum(len(v) for v in subject_docs.values())}")
        print(f"Students: {len(students)}")
        for classroom in classrooms:
            print(f"- {classroom.name}: {len(classroom.students)} students")
    except Exception as exc:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
