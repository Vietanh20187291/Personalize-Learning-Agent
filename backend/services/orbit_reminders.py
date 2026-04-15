from __future__ import annotations

import os
import smtplib
import threading
import time
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from db import models


def _week_bounds(now: datetime) -> Tuple[datetime, datetime]:
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _subject_names(user: models.User) -> List[str]:
    names: List[str] = []
    for classroom in getattr(user, "enrolled_classes", []) or []:
        name = _clean_text(getattr(getattr(classroom, "subject_obj", None), "name", None) or classroom.subject)
        if name and name not in names:
            names.append(name)
    return names


def _study_minutes_between(db: Session, user_id: int, start: datetime, end: datetime) -> int:
    sessions = (
        db.query(models.StudySession)
        .filter(
            models.StudySession.user_id == user_id,
            models.StudySession.start_time >= start,
            models.StudySession.start_time < end,
        )
        .all()
    )
    return int(sum(int(item.duration_minutes or 0) for item in sessions))


def _last_study_at(db: Session, user_id: int) -> Optional[datetime]:
    item = (
        db.query(models.StudySession)
        .filter(models.StudySession.user_id == user_id)
        .order_by(models.StudySession.start_time.desc())
        .first()
    )
    return item.start_time if item else None


def _student_scope(db: Session, teacher_id: Optional[int], class_id: Optional[int]) -> List[models.User]:
    classroom_ids: List[int] = []
    if class_id is not None:
        classroom_ids = [class_id]
    elif teacher_id is not None:
        classroom_ids = [item.id for item in db.query(models.Classroom).filter(models.Classroom.teacher_id == teacher_id).all()]

    if classroom_ids:
        students = (
            db.query(models.User)
            .join(models.enrollment_table, models.enrollment_table.c.user_id == models.User.id)
            .filter(models.enrollment_table.c.class_id.in_(classroom_ids), models.User.role == "student")
            .all()
        )
    else:
        students = db.query(models.User).filter(models.User.role == "student").all()

    unique_students: Dict[int, models.User] = {}
    for student in students:
        unique_students[student.id] = student
    return list(unique_students.values())


def build_weekly_inactivity_report(
    db: Session,
    teacher_id: Optional[int] = None,
    class_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    current_time = now or datetime.utcnow()
    week_start, week_end = _week_bounds(current_time)
    students = _student_scope(db, teacher_id, class_id)

    report_students: List[Dict[str, object]] = []
    inactive_login_count = 0
    inactive_study_count = 0

    for student in students:
        progress = db.query(models.StudentLearningProgress).filter(models.StudentLearningProgress.user_id == student.id).first()
        last_login_at = progress.last_login_at if progress else None
        study_minutes_week = _study_minutes_between(db, student.id, week_start, week_end)
        last_study_at = _last_study_at(db, student.id)

        login_in_week = bool(last_login_at and last_login_at >= week_start)
        study_in_week = study_minutes_week > 0

        if not login_in_week:
            inactive_login_count += 1
        if not study_in_week:
            inactive_study_count += 1

        if login_in_week and study_in_week:
            continue

        report_students.append({
            "user_id": student.id,
            "full_name": student.full_name,
            "email": student.username,
            "student_id": student.student_id,
            "classes": _subject_names(student),
            "last_login_at": last_login_at.isoformat() if last_login_at else None,
            "last_study_at": last_study_at.isoformat() if last_study_at else None,
            "study_minutes_week": study_minutes_week,
            "login_in_week": login_in_week,
            "study_in_week": study_in_week,
            "missing_login": not login_in_week,
            "missing_study": not study_in_week,
        })

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "teacher_id": teacher_id,
        "class_id": class_id,
        "total_students": len(students),
        "inactive_students": len(report_students),
        "inactive_login_students": inactive_login_count,
        "inactive_study_students": inactive_study_count,
        "students": sorted(report_students, key=lambda item: (item["missing_login"], item["missing_study"], item["full_name"] or "")),
    }


def _smtp_settings() -> Dict[str, object]:
    return {
        "host": os.getenv("ORBIT_SMTP_HOST", "").strip(),
        "port": int(os.getenv("ORBIT_SMTP_PORT", "587") or "587"),
        "username": os.getenv("ORBIT_SMTP_USERNAME", "").strip(),
        "password": os.getenv("ORBIT_SMTP_PASSWORD", "").strip(),
        "from_email": os.getenv("ORBIT_SMTP_FROM", "").strip() or os.getenv("ORBIT_SMTP_USERNAME", "").strip(),
        "use_tls": os.getenv("ORBIT_SMTP_USE_TLS", "true").strip().lower() not in ["0", "false", "no"],
    }


def _format_reminder_subject(student: Dict[str, object]) -> str:
    name = _clean_text(str(student.get("full_name") or student.get("email") or "sinh viên"))
    return f"Orbit nhắc học tuần này: {name}"


def _format_reminder_body(student: Dict[str, object], report: Dict[str, object]) -> str:
    classes = student.get("classes") or []
    class_text = ", ".join(classes) if isinstance(classes, list) and classes else "chưa xác định lớp"
    missing_login = "có" if student.get("missing_login") else "không"
    missing_study = "có" if student.get("missing_study") else "không"
    return (
        f"Xin chào {student.get('full_name') or student.get('email') or 'bạn'},\n\n"
        f"Orbit thống kê tuần này cho thấy bạn đang { 'chưa đăng nhập' if student.get('missing_login') else 'đã đăng nhập' } và { 'chưa học đủ' if student.get('missing_study') else 'đã có hoạt động học' } trong tuần hiện tại.\n"
        f"- Số phút học trong tuần: {student.get('study_minutes_week', 0)}\n"
        f"- Lần đăng nhập gần nhất: {student.get('last_login_at') or 'chưa có dữ liệu'}\n"
        f"- Lần học gần nhất: {student.get('last_study_at') or 'chưa có dữ liệu'}\n"
        f"- Lớp/môn liên quan: {class_text}\n\n"
        f"Yêu cầu: hãy đăng nhập và học lại ngay trong tuần này để tránh bị tụt nhịp.\n\n"
        f"Thống kê lớp tuần này:\n"
        f"- Tổng sinh viên: {report.get('total_students', 0)}\n"
        f"- Sinh viên thiếu đăng nhập: {report.get('inactive_login_students', 0)}\n"
        f"- Sinh viên thiếu học: {report.get('inactive_study_students', 0)}\n\n"
        f"Orbit"
    )


def _send_email(settings: Dict[str, object], to_email: str, subject: str, body: str) -> None:
    if not settings.get("host"):
        raise RuntimeError("Thiếu cấu hình SMTP")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = str(settings.get("from_email") or settings.get("username") or "orbit@localhost")
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(str(settings["host"]), int(settings["port"]), timeout=20) as smtp:
        if settings.get("use_tls"):
            smtp.starttls()
        username = str(settings.get("username") or "")
        password = str(settings.get("password") or "")
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)


def send_weekly_reminders(
    db: Session,
    teacher_id: Optional[int] = None,
    class_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    report = build_weekly_inactivity_report(db, teacher_id=teacher_id, class_id=class_id, now=now)
    smtp_settings = _smtp_settings()
    week_start = datetime.fromisoformat(str(report["week_start"]))
    week_end = datetime.fromisoformat(str(report["week_end"]))

    sent_count = 0
    skipped_no_email = 0
    skipped_no_smtp = 0
    failed_count = 0

    for student in report["students"]:
        user_id = int(student["user_id"])
        email = _clean_text(str(student.get("email") or ""))

        existing_log = db.query(models.OrbitWeeklyReminderLog).filter(
            models.OrbitWeeklyReminderLog.user_id == user_id,
            models.OrbitWeeklyReminderLog.week_start == week_start,
        ).first()
        if existing_log and existing_log.status == "sent":
            continue

        if not email:
            skipped_no_email += 1
            if not existing_log:
                db.add(models.OrbitWeeklyReminderLog(
                    user_id=user_id,
                    week_start=week_start,
                    week_end=week_end,
                    email="",
                    status="skipped_no_email",
                    summary="Thiếu email để gửi nhắc nhở.",
                    sent_at=datetime.utcnow(),
                ))
            continue

        subject = _format_reminder_subject(student)
        body = _format_reminder_body(student, report)

        try:
            _send_email(smtp_settings, email, subject, body)
            sent_count += 1
            if existing_log:
                existing_log.status = "sent"
                existing_log.email = email
                existing_log.summary = body
                existing_log.sent_at = datetime.utcnow()
            else:
                db.add(models.OrbitWeeklyReminderLog(
                    user_id=user_id,
                    week_start=week_start,
                    week_end=week_end,
                    email=email,
                    status="sent",
                    summary=body,
                    sent_at=datetime.utcnow(),
                ))
        except Exception as exc:
            failed_count += 1
            if existing_log:
                existing_log.status = "failed"
                existing_log.email = email
                existing_log.summary = f"{body}\n\nLỗi gửi mail: {exc}"
                existing_log.sent_at = datetime.utcnow()
            else:
                db.add(models.OrbitWeeklyReminderLog(
                    user_id=user_id,
                    week_start=week_start,
                    week_end=week_end,
                    email=email,
                    status="failed",
                    summary=f"Lỗi gửi mail: {exc}",
                    sent_at=datetime.utcnow(),
                ))

    if not smtp_settings.get("host"):
        skipped_no_smtp = len(report["students"])

    db.commit()
    return {
        "report": report,
        "sent_count": sent_count,
        "skipped_no_email": skipped_no_email,
        "skipped_no_smtp": skipped_no_smtp,
        "failed_count": failed_count,
    }


def _should_run_now(now: datetime, run_weekday: int = 0, run_hour: int = 8, run_minute: int = 0) -> bool:
    return now.weekday() == run_weekday and (now.hour, now.minute) >= (run_hour, run_minute)


def start_weekly_orbit_reminder_loop(session_factory) -> threading.Thread:
    def _loop() -> None:
        last_run_key: Optional[str] = None
        while True:
            now = datetime.utcnow()
            run_key = now.strftime("%Y-%W")
            if _should_run_now(now) and run_key != last_run_key:
                db = session_factory()
                try:
                    send_weekly_reminders(db)
                    last_run_key = run_key
                except Exception as exc:
                    print(f"❌ Orbit weekly reminder job failed: {exc}")
                    db.rollback()
                finally:
                    db.close()

            time.sleep(3600)

    thread = threading.Thread(target=_loop, name="orbit-weekly-reminder", daemon=True)
    thread.start()
    return thread