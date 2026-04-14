#!/usr/bin/env python
"""Seed test data for Nova debugging.

Creates:
- 4 subjects
- 8 classes (2 per subject)
- 20 students
- Each student joins 3 or 4 classes
- Assessment history records with scores for every enrollment

The script is idempotent enough for repeated runs:
- It reuses existing users/subjects/classes when found
- It removes conflicting enrollments within the same subject before re-adding
- It skips duplicated seed assessment rows using a marker in wrong_detail
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

SEED_MARKER = "seed_nova_test_data_v1"
SUBJECTS = [
    "Cơ sở Hệ điều hành",
    "Vi xử lý",
    "Cơ sở dữ liệu",
    "Mạng máy tính",
]

CLASS_SUFFIXES = ["Lớp A", "Lớp B"]


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


def get_or_create_student(db, index: int) -> models.User:
    username = f"nova_student_{index:02d}"
    student = db.query(models.User).filter(models.User.username == username).first()
    if student:
        return student

    student = models.User(
        username=username,
        hashed_password=hash_password("NovaStudent@123"),
        role="student",
        full_name=f"Sinh viên Nova {index:02d}",
        student_id=f"NV{202600 + index:03d}",
    )
    db.add(student)
    db.flush()
    return student


def assign_target_classes() -> Dict[int, List[int]]:
    """Return subject indexes each student should join.

    Students 1-10 join 4 subjects.
    Students 11-20 join 3 subjects (miss one different subject each).
    This yields balanced class sizes around 8-9 students per class.
    """
    target = {student_idx: [0, 1, 2, 3] for student_idx in range(1, 21)}

    # Ten students miss exactly one subject -> each student still in 3-4 classes.
    missing_subject_by_student = {
        11: 3,
        12: 3,
        13: 3,
        14: 2,
        15: 2,
        16: 2,
        17: 1,
        18: 1,
        19: 0,
        20: 0,
    }

    for student_idx, missing_subject_idx in missing_subject_by_student.items():
        target[student_idx] = [s for s in target[student_idx] if s != missing_subject_idx]

    return target


def score_for(student_idx: int, subject_idx: int, phase: str) -> float:
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


def clear_seed_subject_enrollments(student: models.User, seed_subject_ids: set[int]):
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


def main():
    db = SessionLocal()
    try:
        teacher = get_or_create_teacher(db)
        subjects = [get_or_create_subject(db, name) for name in SUBJECTS]
        classrooms = []
        for subject in subjects:
            for suffix in CLASS_SUFFIXES:
                classrooms.append(get_or_create_classroom(db, subject, teacher, suffix))

        target_subject_indexes = assign_target_classes()
        students: List[models.User] = []
        seed_subject_ids = {subject.id for subject in subjects}

        for student_idx in range(1, 21):
            student = get_or_create_student(db, student_idx)
            students.append(student)
            clear_seed_subject_enrollments(student, seed_subject_ids)

            for subject_idx in target_subject_indexes[student_idx]:
                subject = subjects[subject_idx]
                # Deterministic split to keep class counts balanced for each subject.
                class_variant = "Lớp A" if (student_idx + subject_idx) % 2 == 0 else "Lớp B"
                classroom = next(
                    item for item in classrooms
                    if item.subject_id == subject.id and item.name == f"{subject.name} - {class_variant}"
                )
                ensure_single_subject_enrollment(student, classroom)
                create_assessment_rows(db, student, subject, student_idx, subject_idx)

        db.commit()

        print("Seed Nova test data completed")
        print(f"Teacher: {teacher.username} (id={teacher.id})")
        print(f"Subjects: {len(subjects)}")
        print(f"Classes: {len(classrooms)}")
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
