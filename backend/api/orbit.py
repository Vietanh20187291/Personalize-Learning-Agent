from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.orbit_agent import OrbitAgent
from db import models
from db.database import get_db

router = APIRouter()


class OrbitChatRequest(BaseModel):
    user_id: int
    subject: str
    message: str
    class_id: Optional[int] = None
    document_id: Optional[int] = None
    source_file: Optional[str] = None


class OrbitProgressResponse(BaseModel):
    lessons_total: int
    lessons_week: int
    lessons_month: int
    study_minutes_total: int
    study_minutes_week: int
    study_minutes_month: int
    tests_total: int
    tests_week: int
    tests_month: int
    orbit_questions_total: int
    orbit_questions_week: int
    orbit_chat_minutes_total: int
    orbit_chat_minutes_week: int


class TeacherDirectiveRequest(BaseModel):
    teacher_id: int
    student_id: int
    class_id: Optional[int] = None
    subject: Optional[str] = None
    target_tests: int = 0
    target_chapters: int = 0
    note: str = ""


def _week_bounds(now: datetime):
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


def _month_start(now: datetime):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _subject_name_of_classroom(classroom: models.Classroom) -> str:
    return (getattr(getattr(classroom, "subject_obj", None), "name", None) or classroom.subject or "").strip()


def _collect_subject_learning_map(db: Session, user: models.User) -> Dict[str, Dict[str, int]]:
    data: Dict[str, Dict[str, int]] = {}

    for classroom in getattr(user, "enrolled_classes", []):
        subject_name = _subject_name_of_classroom(classroom)
        if not subject_name:
            continue
        key = _normalize(subject_name)
        if key not in data:
            data[key] = {
                "subject_name": subject_name,
                "study_minutes": 0,
                "tests": 0,
                "lessons": 0,
            }

    sessions = db.query(models.StudySession).filter(models.StudySession.user_id == user.id).all()
    for item in sessions:
        subject_name = (getattr(getattr(item, "subject_obj", None), "name", None) or item.subject or "").strip()
        if not subject_name:
            continue
        key = _normalize(subject_name)
        if key not in data:
            data[key] = {
                "subject_name": subject_name,
                "study_minutes": 0,
                "tests": 0,
                "lessons": 0,
            }
        data[key]["study_minutes"] += int(item.duration_minutes or 0)

    histories = db.query(models.AssessmentHistory).filter(models.AssessmentHistory.user_id == user.id).all()
    for item in histories:
        subject_name = (getattr(getattr(item, "subject_obj", None), "name", None) or item.subject or "").strip()
        if not subject_name:
            continue
        key = _normalize(subject_name)
        if key not in data:
            data[key] = {
                "subject_name": subject_name,
                "study_minutes": 0,
                "tests": 0,
                "lessons": 0,
            }
        data[key]["tests"] += 1
        if float(item.score or 0) >= 60 and (item.test_type in ["chapter", "session"]):
            data[key]["lessons"] += 1

    return data


def _pick_focus_subject(db: Session, user: models.User) -> Optional[str]:
    subject_map = _collect_subject_learning_map(db, user)
    if not subject_map:
        return None

    ranked = sorted(
        subject_map.values(),
        key=lambda item: (
            item.get("lessons", 0) > 0,
            item.get("tests", 0) > 0,
            item.get("study_minutes", 0),
        ),
    )
    return ranked[0]["subject_name"] if ranked else None


def _resolve_classroom_for_subject(user: models.User, subject_name: str) -> Optional[models.Classroom]:
    key = _normalize(subject_name)
    for item in getattr(user, "enrolled_classes", []):
        if _normalize(_subject_name_of_classroom(item)) == key:
            return item
    return None


def _pick_recommended_document(db: Session, user: models.User, subject_name: str) -> Optional[models.Document]:
    classroom = _resolve_classroom_for_subject(user, subject_name)
    if classroom is None:
        return None

    docs = db.query(models.Document).filter(models.Document.class_id == classroom.id).order_by(models.Document.upload_time.asc()).all()
    if not docs:
        return None

    # Ưu tiên tài liệu sinh viên chưa mở trong Orbit trước đó.
    opened_filenames = {
        (item.content or "").strip().lower()
        for item in db.query(models.OrbitChatMessage).filter(
            models.OrbitChatMessage.user_id == user.id,
            models.OrbitChatMessage.role == "assistant",
        ).all()
        if (item.content or "").strip()
    }
    for doc in docs:
        if (doc.filename or "").strip().lower() not in opened_filenames:
            return doc

    # fallback: lấy tài liệu đầu tiên của môn/lớp.
    return docs[0]


def _quick_document_summary(db: Session, document: models.Document) -> Dict[str, object]:
    chunks = db.query(models.Chunk).filter(
        models.Chunk.subject_id == document.subject_id,
        models.Chunk.source_file == document.filename,
    ).order_by(models.Chunk.id.asc()).limit(4).all()

    if not chunks:
        return {
            "title": document.title or document.filename,
            "summary": f"Tài liệu {document.filename}: hãy đọc phần mở đầu, khái niệm cốt lõi, ví dụ minh họa và phần kết luận.",
            "key_points": [
                "Xác định định nghĩa và thuật ngữ chính",
                "Nắm quy trình/thuật toán quan trọng",
                "Làm ít nhất 3 câu tự kiểm tra sau khi học",
            ],
        }

    merged = "\n".join([(item.content or "").strip() for item in chunks if (item.content or "").strip()])
    merged = merged[:1000]

    lines = [ln.strip() for ln in merged.splitlines() if ln.strip()]
    key_points = lines[:3] if lines else []

    summary_text = merged if merged else f"Tài liệu {document.filename} có nội dung cốt lõi cần học ngay."
    return {
        "title": document.title or document.filename,
        "summary": summary_text,
        "key_points": key_points,
    }


def _should_recommend_study(message: str) -> bool:
    text = _normalize(message)
    return any(token in text for token in [
        "nên học gì", "nen hoc gi", "môn nào chưa học", "mon nao chua hoc", "học môn nào", "hoc mon nao", "quên học", "quen hoc", "học ít", "hoc it"
    ])


def _is_summary_request(message: str) -> bool:
    text = _normalize(message)
    return any(token in text for token in ["tóm tắt", "tom tat", "tóm lược", "tom luoc", "summary"])


def _build_recommendation_payload(db: Session, user: models.User) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    focus_subject = _pick_focus_subject(db, user)
    if not focus_subject:
        return None, None

    document = _pick_recommended_document(db, user, focus_subject)
    if not document:
        return {
            "subject": focus_subject,
            "reason": "Môn này đang học ít/chưa học, nhưng hiện chưa có tài liệu để mở.",
        }, (
            f"Tôi đề xuất ưu tiên học môn {focus_subject} vì bạn đang học ít/chưa học môn này. "
            "Hiện chưa có tài liệu khả dụng để mở tự động, bạn hãy nhờ giảng viên cập nhật học liệu."
        )

    summary = _quick_document_summary(db, document)
    payload: Dict[str, object] = {
        "subject": focus_subject,
        "reason": "Môn này đang học ít/chưa học so với các môn còn lại.",
        "document": {
            "id": document.id,
            "filename": document.filename,
            "subject": focus_subject,
            "class_id": document.class_id,
            "summary": summary,
        },
    }
    text = (
        f"Tôi đề xuất học môn {focus_subject} trước vì đây là môn bạn đang học ít/chưa học. "
        f"Tôi đã chọn tài liệu {document.filename} để bạn bắt đầu ngay."
    )
    return payload, text


def _get_or_create_orbit_session(db: Session, user_id: int, class_id: Optional[int], subject_id: Optional[int]) -> models.OrbitChatSession:
    now = datetime.utcnow()
    active_threshold = now - timedelta(minutes=15)
    session = db.query(models.OrbitChatSession).filter(
        models.OrbitChatSession.user_id == user_id,
        models.OrbitChatSession.last_message_at >= active_threshold,
    ).order_by(models.OrbitChatSession.last_message_at.desc()).first()

    if session:
        return session

    session = models.OrbitChatSession(
        user_id=user_id,
        class_id=class_id,
        subject_id=subject_id,
        started_at=now,
        last_message_at=now,
        ended_at=now,
        message_count=0,
    )
    db.add(session)
    db.flush()
    return session


def _sync_learning_progress(db: Session, user_id: int):
    now = datetime.utcnow()

    total_lessons = db.query(models.AssessmentHistory).filter(
        models.AssessmentHistory.user_id == user_id,
        models.AssessmentHistory.test_type.in_(["chapter", "session"]),
        models.AssessmentHistory.score >= 60,
    ).count()

    total_tests = db.query(models.AssessmentHistory).filter(models.AssessmentHistory.user_id == user_id).count()
    total_study = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(models.StudySession.user_id == user_id).all())

    total_msgs = db.query(models.OrbitChatMessage).filter(
        models.OrbitChatMessage.user_id == user_id,
        models.OrbitChatMessage.role == "user",
    ).count()

    total_chat_sec = 0
    for item in db.query(models.OrbitChatSession).filter(models.OrbitChatSession.user_id == user_id).all():
        if item.started_at and item.ended_at and item.ended_at >= item.started_at:
            total_chat_sec += int((item.ended_at - item.started_at).total_seconds())

    progress = db.query(models.StudentLearningProgress).filter(models.StudentLearningProgress.user_id == user_id).first()
    if not progress:
        progress = models.StudentLearningProgress(user_id=user_id)
        db.add(progress)

    progress.lessons_completed_total = int(total_lessons)
    progress.tests_completed_total = int(total_tests)
    progress.total_study_minutes = int(total_study)
    progress.total_agent_messages = int(total_msgs)
    progress.total_agent_chat_seconds = int(total_chat_sec)
    progress.last_active_at = now


def _build_progress_payload(db: Session, user_id: int) -> OrbitProgressResponse:
    now = datetime.utcnow()
    week_start, _ = _week_bounds(now)
    month_start = _month_start(now)

    lessons_total = db.query(models.AssessmentHistory).filter(
        models.AssessmentHistory.user_id == user_id,
        models.AssessmentHistory.test_type.in_(["chapter", "session"]),
        models.AssessmentHistory.score >= 60,
    ).count()
    lessons_week = db.query(models.AssessmentHistory).filter(
        models.AssessmentHistory.user_id == user_id,
        models.AssessmentHistory.test_type.in_(["chapter", "session"]),
        models.AssessmentHistory.score >= 60,
        models.AssessmentHistory.timestamp >= week_start,
    ).count()
    lessons_month = db.query(models.AssessmentHistory).filter(
        models.AssessmentHistory.user_id == user_id,
        models.AssessmentHistory.test_type.in_(["chapter", "session"]),
        models.AssessmentHistory.score >= 60,
        models.AssessmentHistory.timestamp >= month_start,
    ).count()

    study_total = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(models.StudySession.user_id == user_id).all())
    study_week = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(
        models.StudySession.user_id == user_id,
        models.StudySession.start_time >= week_start,
    ).all())
    study_month = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(
        models.StudySession.user_id == user_id,
        models.StudySession.start_time >= month_start,
    ).all())

    tests_total = db.query(models.AssessmentHistory).filter(models.AssessmentHistory.user_id == user_id).count()
    tests_week = db.query(models.AssessmentHistory).filter(
        models.AssessmentHistory.user_id == user_id,
        models.AssessmentHistory.timestamp >= week_start,
    ).count()
    tests_month = db.query(models.AssessmentHistory).filter(
        models.AssessmentHistory.user_id == user_id,
        models.AssessmentHistory.timestamp >= month_start,
    ).count()

    orbit_questions_total = db.query(models.OrbitChatMessage).filter(
        models.OrbitChatMessage.user_id == user_id,
        models.OrbitChatMessage.role == "user",
    ).count()
    orbit_questions_week = db.query(models.OrbitChatMessage).filter(
        models.OrbitChatMessage.user_id == user_id,
        models.OrbitChatMessage.role == "user",
        models.OrbitChatMessage.created_at >= week_start,
    ).count()

    orbit_chat_minutes_total = 0
    orbit_chat_minutes_week = 0
    sessions: List[models.OrbitChatSession] = db.query(models.OrbitChatSession).filter(models.OrbitChatSession.user_id == user_id).all()
    for item in sessions:
        if not item.started_at or not item.ended_at or item.ended_at < item.started_at:
            continue
        minutes = int((item.ended_at - item.started_at).total_seconds() // 60)
        orbit_chat_minutes_total += minutes
        if item.started_at >= week_start:
            orbit_chat_minutes_week += minutes

    return OrbitProgressResponse(
        lessons_total=int(lessons_total),
        lessons_week=int(lessons_week),
        lessons_month=int(lessons_month),
        study_minutes_total=int(study_total),
        study_minutes_week=int(study_week),
        study_minutes_month=int(study_month),
        tests_total=int(tests_total),
        tests_week=int(tests_week),
        tests_month=int(tests_month),
        orbit_questions_total=int(orbit_questions_total),
        orbit_questions_week=int(orbit_questions_week),
        orbit_chat_minutes_total=int(orbit_chat_minutes_total),
        orbit_chat_minutes_week=int(orbit_chat_minutes_week),
    )


@router.post("/chat")
def chat_with_orbit(req: OrbitChatRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Orbit chỉ dành cho tài khoản sinh viên")

    subject_name = (req.subject or "").strip()
    if not subject_name:
        raise HTTPException(status_code=400, detail="Thiếu môn học")

    subject = db.query(models.Subject).filter(models.Subject.name.ilike(subject_name)).first()
    if not subject:
        subject = models.Subject(name=subject_name, description=f"Môn {subject_name}")
        db.add(subject)
        db.flush()

    classroom = None
    if req.class_id:
        classroom = db.query(models.Classroom).filter(models.Classroom.id == req.class_id).first()
    if classroom is None:
        classroom = next((item for item in getattr(user, "enrolled_classes", []) if (item.subject or "").strip().lower() == subject_name.lower()), None)

    if classroom is None:
        raise HTTPException(status_code=400, detail=f"Bạn chưa tham gia lớp cho môn {subject_name}")

    orbit = OrbitAgent(db)
    reply = orbit.respond(user=user, subject_name=subject_name, message=req.message, class_id=classroom.id)

    recommendation_payload: Optional[Dict[str, object]] = None
    action_metadata: Optional[Dict[str, object]] = None

    selected_doc: Optional[models.Document] = None
    if req.document_id:
        selected_doc = db.query(models.Document).filter(models.Document.id == req.document_id).first()
    elif (req.source_file or "").strip():
        selected_doc = db.query(models.Document).filter(
            models.Document.class_id == classroom.id,
            models.Document.filename == req.source_file.strip(),
        ).first()

    if _should_recommend_study(req.message):
        recommendation_payload, recommendation_text = _build_recommendation_payload(db, user)
        if recommendation_text:
            reply = f"{reply}\n\n{recommendation_text}"

        rec_doc = ((recommendation_payload or {}).get("document") or {}) if recommendation_payload else {}
        rec_doc_id = rec_doc.get("id") if isinstance(rec_doc, dict) else None
        if rec_doc_id:
            action_metadata = {
                "action_type": "open_document",
                "target": "student",
                "tab_name": "adaptive",
                "params": {
                    "subject": rec_doc.get("subject") or (recommendation_payload or {}).get("subject"),
                    "document_id": rec_doc.get("id"),
                    "class_id": rec_doc.get("class_id"),
                    "filename": rec_doc.get("filename"),
                    "summary": rec_doc.get("summary"),
                },
                "should_auto_execute": True,
            }

    if _is_summary_request(req.message):
        summary_doc = selected_doc
        if summary_doc is None and recommendation_payload:
            rec_doc = (recommendation_payload.get("document") or {}) if isinstance(recommendation_payload, dict) else {}
            rec_id = rec_doc.get("id") if isinstance(rec_doc, dict) else None
            if rec_id:
                summary_doc = db.query(models.Document).filter(models.Document.id == int(rec_id)).first()

        if summary_doc is None:
            summary_doc = _pick_recommended_document(db, user, subject_name)

        if summary_doc is not None:
            sum_data = _quick_document_summary(db, summary_doc)
            sum_lines = [
                f"Tóm tắt tài liệu {summary_doc.filename}:",
                f"- Nội dung chính: {sum_data.get('summary', '')}",
            ]
            key_points = sum_data.get("key_points") or []
            if isinstance(key_points, list) and key_points:
                sum_lines.append("- Ý quan trọng:")
                sum_lines.extend([f"  • {str(item)}" for item in key_points[:4]])
            reply = f"{reply}\n\n" + "\n".join(sum_lines)
            action_metadata = action_metadata or {
                "action_type": "open_document",
                "target": "student",
                "tab_name": "adaptive",
                "params": {
                    "subject": (getattr(summary_doc.subject_obj, "name", None) or summary_doc.subject or subject_name),
                    "document_id": summary_doc.id,
                    "class_id": summary_doc.class_id,
                    "filename": summary_doc.filename,
                    "summary": sum_data,
                },
                "should_auto_execute": True,
            }

    now = datetime.utcnow()
    session = _get_or_create_orbit_session(db, user.id, classroom.id, subject.id)

    user_msg = models.OrbitChatMessage(
        session_id=session.id,
        user_id=user.id,
        role="user",
        content=req.message,
        created_at=now,
    )
    assistant_msg = models.OrbitChatMessage(
        session_id=session.id,
        user_id=user.id,
        role="assistant",
        content=reply,
        created_at=now,
    )
    db.add(user_msg)
    db.add(assistant_msg)

    session.message_count = int(session.message_count or 0) + 2
    session.last_message_at = now
    session.ended_at = now

    _sync_learning_progress(db, user.id)
    db.commit()

    return {
        "reply": reply,
        "agent_name": "Orbit Agent",
        "class_id": classroom.id,
        "subject": subject_name,
        "recommendation": recommendation_payload,
        "action_metadata": action_metadata,
    }


@router.get("/progress/{user_id}", response_model=OrbitProgressResponse)
def get_orbit_progress(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Chỉ sinh viên mới có thống kê Orbit")

    return _build_progress_payload(db, user_id)


@router.post("/teacher-directive")
def create_teacher_directive(req: TeacherDirectiveRequest, db: Session = Depends(get_db)):
    teacher = db.query(models.User).filter(models.User.id == req.teacher_id).first()
    student = db.query(models.User).filter(models.User.id == req.student_id).first()
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=403, detail="teacher_id không hợp lệ")
    if not student or student.role != "student":
        raise HTTPException(status_code=400, detail="student_id không hợp lệ")

    subject_id = None
    if (req.subject or "").strip():
        subject = db.query(models.Subject).filter(models.Subject.name.ilike(req.subject.strip())).first()
        if subject:
            subject_id = subject.id

    now = datetime.utcnow()
    week_start, week_end = _week_bounds(now)

    directive = models.OrbitCoachDirective(
        teacher_id=req.teacher_id,
        student_id=req.student_id,
        class_id=req.class_id,
        subject_id=subject_id,
        target_tests=max(0, int(req.target_tests or 0)),
        target_chapters=max(0, int(req.target_chapters or 0)),
        note=(req.note or "").strip() or None,
        week_start=week_start,
        week_end=week_end,
        is_active=True,
    )
    db.add(directive)
    db.commit()

    return {
        "message": "Đã giao chỉ tiêu tuần cho Orbit",
        "directive_id": directive.id,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
    }
