from datetime import datetime, timedelta
import logging
import unicodedata
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.adaptive_agent import AdaptiveAgent
from agents.orbit_agent import OrbitAgent
from db import models
from db.database import get_db
from logging_config import error_json_response
from services.orbit_reminders import build_weekly_inactivity_report, send_weekly_reminders

router = APIRouter()
logger = logging.getLogger("app.orbit")


class OrbitChatRequest(BaseModel):
    user_id: int
    subject: str
    message: str
    class_id: Optional[int] = None
    document_id: Optional[int] = None
    source_file: Optional[str] = None
    session_id: Optional[int] = None


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


class WeeklyInactivityQuery(BaseModel):
    teacher_id: Optional[int] = None
    class_id: Optional[int] = None


class OrbitHistoryMessage(BaseModel):
    role: str
    content: str
    created_at: str


class OrbitHistoryResponse(BaseModel):
    session_id: Optional[int]
    messages: List[OrbitHistoryMessage]


def _week_bounds(now: datetime):
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


def _month_start(now: datetime):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _normalize_ascii(text: str) -> str:
    value = _normalize(text)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(value.split())


def _is_all_subject(text: str) -> bool:
    key = _normalize(text)
    return key in {"", "all", "tat ca", "tất cả", "all subjects", "all-subjects"}


def _subject_name_of_classroom(classroom: models.Classroom) -> str:
    return (getattr(getattr(classroom, "subject_obj", None), "name", None) or classroom.subject or "").strip()


def _collect_subject_learning_map(db: Session, user: models.User) -> Dict[str, Dict[str, int]]:
    data: Dict[str, Dict[str, object]] = {}

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
                "latest_score": None,
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
                "latest_score": None,
            }
        data[key]["study_minutes"] += int(item.duration_minutes or 0)

    subjects = {
        item.id: item.name
        for item in db.query(models.Subject).all()
    }

    eval_rows = db.query(models.StudentDocumentEvaluation).filter(
        models.StudentDocumentEvaluation.user_id == user.id,
    ).all()
    for item in eval_rows:
        subject_name = (subjects.get(item.subject_id) or "").strip()
        if not subject_name:
            continue
        key = _normalize(subject_name)
        if key not in data:
            data[key] = {
                "subject_name": subject_name,
                "study_minutes": 0,
                "tests": 0,
                "lessons": 0,
                "latest_score": None,
                "_score_sum": 0.0,
                "_score_count": 0,
            }

        if "_score_sum" not in data[key]:
            data[key]["_score_sum"] = 0.0
            data[key]["_score_count"] = 0

        data[key]["tests"] += int(item.attempts or 0)
        if bool(item.is_completed):
            data[key]["lessons"] += 1
        if int(item.attempts or 0) > 0:
            data[key]["_score_sum"] += float(item.latest_score or 0.0)
            data[key]["_score_count"] += 1

    for item in data.values():
        score_count = int(item.get("_score_count", 0) or 0)
        if score_count > 0:
            item["latest_score"] = float(item.get("_score_sum", 0.0) or 0.0) / score_count
        item.pop("_score_sum", None)
        item.pop("_score_count", None)

    return data


def _focus_priority(item: Dict[str, object]) -> Tuple[int, int, int, int]:
    latest_score = item.get("latest_score")
    if latest_score is None:
        score_bucket = 0
    else:
        score_value = float(latest_score)
        if score_value < 50:
            score_bucket = 1
        elif score_value < 65:
            score_bucket = 2
        else:
            score_bucket = 3

    return (
        score_bucket,
        int(item.get("lessons", 0)),
        int(item.get("tests", 0)),
        int(item.get("study_minutes", 0)),
    )


def _pick_focus_subject(db: Session, user: models.User) -> Optional[str]:
    subject_map = _collect_subject_learning_map(db, user)
    if not subject_map:
        return None

    ranked = sorted(
        subject_map.values(),
        key=lambda item: (
            0 if _has_available_documents_for_subject(db, user, str(item.get("subject_name") or "")) else 1,
            *_focus_priority(item),
        ),
    )
    return ranked[0]["subject_name"] if ranked else None


def _resolve_classroom_for_subject(user: models.User, subject_name: str) -> Optional[models.Classroom]:
    key = _normalize(subject_name)
    for item in getattr(user, "enrolled_classes", []):
        if _normalize(_subject_name_of_classroom(item)) == key:
            return item
    return None


def _available_documents_for_classroom(db: Session, classroom: models.Classroom) -> List[models.Document]:
    return db.query(models.Document).join(
        models.DocumentPublication,
        models.DocumentPublication.doc_id == models.Document.id,
    ).filter(
        models.Document.class_id == classroom.id,
        models.DocumentPublication.is_visible_to_students == True,
    ).order_by(models.Document.upload_time.asc()).all()


def _has_available_documents_for_subject(db: Session, user: models.User, subject_name: str) -> bool:
    classroom = _resolve_classroom_for_subject(user, subject_name)
    if classroom is None:
        return False
    return len(_available_documents_for_classroom(db, classroom)) > 0


def _pick_recommended_document(db: Session, user: models.User, subject_name: str) -> Optional[models.Document]:
    classroom = _resolve_classroom_for_subject(user, subject_name)
    if classroom is None:
        return None

    docs = _available_documents_for_classroom(db, classroom)
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


def _pick_document_by_evaluation(db: Session, user: models.User, subject_name: str) -> Tuple[Optional[models.Document], str]:
    classroom = _resolve_classroom_for_subject(user, subject_name)
    if classroom is None:
        return None, "Bạn chưa có lớp tương ứng để gợi ý tài liệu."

    docs = [
        doc for doc in _available_documents_for_classroom(db, classroom)
        if doc.subject_id == classroom.subject_id
    ]

    if not docs:
        return None, "Môn này chưa có tài liệu trong lớp học của bạn."

    eval_map: Dict[int, models.StudentDocumentEvaluation] = {
        item.document_id: item
        for item in db.query(models.StudentDocumentEvaluation).filter(
            models.StudentDocumentEvaluation.user_id == user.id,
            models.StudentDocumentEvaluation.class_id == classroom.id,
            models.StudentDocumentEvaluation.subject_id == classroom.subject_id,
        ).all()
    }

    missing_docs = [doc for doc in docs if doc.id not in eval_map or int(getattr(eval_map.get(doc.id), "attempts", 0) or 0) == 0]
    if missing_docs:
        return missing_docs[0], "Bạn chưa làm bài kiểm tra cho tài liệu này."

    low_docs = sorted(
        [doc for doc in docs if float(getattr(eval_map.get(doc.id), "latest_score", 100.0) or 100.0) < 60.0],
        key=lambda doc: float(getattr(eval_map.get(doc.id), "latest_score", 100.0) or 100.0),
    )
    if low_docs:
        score = float(getattr(eval_map.get(low_docs[0].id), "latest_score", 0.0) or 0.0)
        return low_docs[0], f"Điểm kiểm tra gần nhất của tài liệu này còn thấp ({score:.1f})."

    weak_docs = sorted(
        docs,
        key=lambda doc: float(getattr(eval_map.get(doc.id), "latest_score", 100.0) or 100.0),
    )
    score = float(getattr(eval_map.get(weak_docs[0].id), "latest_score", 0.0) or 0.0)
    return weak_docs[0], f"Tài liệu này có điểm thấp nhất trong các tài liệu đã kiểm tra ({score:.1f})."


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
        "nên học gì", "nen hoc gi", "môn nào chưa học", "mon nao chua hoc", "học môn nào", "hoc mon nao", "quên học", "quen hoc", "học ít", "hoc it",
        "học gì tiếp", "hoc gi tiep", "nên học tài liệu nào", "nen hoc tai lieu nao", "tài liệu nào", "tai lieu nao", "điểm thấp", "diem thap", "đề xuất học", "de xuat hoc"
    ])


def _is_progress_overview_request(message: str) -> bool:
    text = _normalize(message)
    return any(token in text for token in [
        "thành tích học tập", "thanh tich hoc tap", "kết quả học tập", "ket qua hoc tap", "kết quả của tôi", "ket qua cua toi",
        "học tập thế nào", "hoc tap the nao", "tôi học thế nào", "toi hoc the nao", "điểm tôi", "diem toi", "báo cáo học tập", "bao cao hoc tap"
    ])


def _first_available_document_for_subject(db: Session, user: models.User, subject_name: str) -> Tuple[Optional[models.Document], Optional[models.Classroom]]:
    classroom = _resolve_classroom_for_subject(user, subject_name)
    if classroom is None:
        return None, None

    docs = _available_documents_for_classroom(db, classroom)
    if not docs:
        return None, classroom

    return docs[0], classroom


def _is_summary_request(message: str) -> bool:
    text = _normalize(message)
    return any(token in text for token in [
        "tóm tắt", "tom tat", "tóm lược", "tom luoc", "summary", "summarize"
    ])


def _is_document_followup_request(message: str) -> bool:
    text = _normalize(message)
    return any(token in text for token in [
        "tóm tắt", "tom tat", "tóm lược", "tom luoc", "summary", "summarize",
        "ý chính", "y chinh", "nội dung chính", "noi dung chinh",
        "main idea", "main ideas", "key point", "key points",
        "giải thích", "giai thich", "explain", "phân tích", "phan tich",
    ])


def _is_document_learning_request(message: str, selected_doc: Optional[models.Document]) -> bool:
    if selected_doc is None:
        return False

    if _is_document_followup_request(message):
        return True

    if _is_open_document_request(message) or _is_progress_or_plan_request(message):
        return False

    if _should_recommend_study(message) or _is_progress_overview_request(message):
        return False

    if _is_entry_message(message):
        return False

    return bool((message or "").strip())


def _resolve_selected_document(
    db: Session,
    user: models.User,
    classroom: Optional[models.Classroom],
    document_id: Optional[int],
    source_file: Optional[str],
) -> Optional[models.Document]:
    selected_doc: Optional[models.Document] = None
    if document_id:
        selected_doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    elif (source_file or "").strip():
        query = db.query(models.Document).filter(models.Document.filename == source_file.strip())
        if classroom is not None:
            query = query.filter(models.Document.class_id == classroom.id)
        selected_doc = query.first()

    if selected_doc is None:
        return None

    enrolled_class_ids = {item.id for item in getattr(user, "enrolled_classes", []) or []}
    if selected_doc.class_id and selected_doc.class_id in enrolled_class_ids:
        return selected_doc

    return None


def _recover_selected_document_from_history(
    db: Session,
    user: models.User,
    classroom: Optional[models.Classroom],
    session_id: Optional[int],
) -> Optional[models.Document]:
    if classroom is None:
        return None

    allowed_docs = _available_documents_for_classroom(db, classroom)
    if not allowed_docs:
        return None

    candidates = []
    for doc in allowed_docs:
        filename = (doc.filename or "").strip()
        title = (doc.title or "").strip()
        if not filename and not title:
            continue
        candidates.append((doc, _normalize(filename), _normalize(title)))

    _, recent_messages = _get_recent_orbit_messages(db, user.id, session_id=session_id, limit=24)
    for item in reversed(recent_messages):
        content = _normalize(str(item.get("content", "")))
        if not content:
            continue
        for doc, filename_key, title_key in candidates:
            if filename_key and filename_key in content:
                return doc
            if title_key and title_key in content:
                return doc

    return None


def _reply_with_open_document_context(
    db: Session,
    user: models.User,
    classroom: models.Classroom,
    subject_name: str,
    selected_doc: models.Document,
    message: str,
    session_id: Optional[int] = None,
) -> str:
    allowed_docs = _available_documents_for_classroom(db, classroom)
    allowed_filenames = [item.filename for item in allowed_docs if (item.filename or "").strip()]
    if selected_doc.filename and selected_doc.filename not in allowed_filenames:
        allowed_filenames.append(selected_doc.filename)

    _, recent_messages = _get_recent_orbit_messages(db, user.id, session_id=session_id, limit=16)
    history = [
        {"role": item.get("role"), "content": item.get("content", "")}
        for item in recent_messages
        if item.get("role") in {"user", "assistant"} and str(item.get("content", "")).strip()
    ]

    summary = _quick_document_summary(db, selected_doc)
    key_points = summary.get("key_points") or []
    key_points_text = "\n".join([f"- {str(item)}" for item in key_points[:4]]) if isinstance(key_points, list) and key_points else "- Bám vào các khái niệm cốt lõi và ví dụ trong tài liệu."
    roadmap_context = (
        f"Tài liệu đang mở: {selected_doc.filename}. "
        f"Hỗ trợ người học bám sát tài liệu này, không lái sang tài liệu khác.\n"
        f"Tóm tắt nhanh: {str(summary.get('summary', ''))[:900]}\n"
        f"Ý chính:\n{key_points_text}"
    )

    agent = AdaptiveAgent(db)
    response = agent.chat_with_tutor(
        subject=subject_name,
        user_message=message,
        roadmap_context=roadmap_context,
        allowed_filenames=allowed_filenames,
        session_topic=(selected_doc.title or selected_doc.filename or "").strip(),
        source_file=(selected_doc.filename or "").strip(),
        history=history,
        document_id=selected_doc.id,
        user_id=user.id,
    )
    return str(response or "").strip()


def _is_entry_message(message: str) -> bool:
    text = _normalize(message)
    text_ascii = _normalize_ascii(message)
    keywords = [
        "bắt đầu bài học", "bat dau bai hoc", "bắt đầu học", "bat dau hoc",
        "chào ai", "chao ai", "học hôm nay", "hoc hom nay", "hello orbit",
        "bat dau", "start learning", "start study", "start orbit",
        "b?t d?u", "b?t d?u b", "bai h?c",
    ]
    if any(token in text for token in keywords) or any(token in text_ascii for token in keywords):
        return True

    # Fallback cho trường hợp text tiếng Việt bị lỗi mã hóa kiểu "b?t d?u b?i h?c".
    if "b?t" in text and ("d?u" in text or "h?c" in text or "b?i" in text):
        return True

    return False


def _overall_latest_score(db: Session, user_id: int) -> Optional[float]:
    rows = db.query(models.StudentDocumentEvaluation).filter(
        models.StudentDocumentEvaluation.user_id == user_id,
        models.StudentDocumentEvaluation.attempts > 0,
    ).all()
    if not rows:
        return None
    scores = [float(item.latest_score or 0.0) for item in rows]
    return sum(scores) / len(scores) if scores else None


def _latest_login_at(db: Session, user_id: int) -> Optional[datetime]:
    latest_login = db.query(models.UserLoginSession).filter(
        models.UserLoginSession.user_id == user_id,
    ).order_by(models.UserLoginSession.login_at.desc()).first()

    progress = db.query(models.StudentLearningProgress).filter(
        models.StudentLearningProgress.user_id == user_id,
    ).first()
    user = db.query(models.User).filter(models.User.id == user_id).first()

    candidates: List[datetime] = []
    if latest_login and latest_login.login_at:
        candidates.append(latest_login.login_at)
    if progress and progress.last_login_at:
        candidates.append(progress.last_login_at)
    if user and user.last_login_at:
        candidates.append(user.last_login_at)

    if not candidates:
        return None
    return max(candidates)


def _entry_orbit_mode(db: Session, user_id: int, now: Optional[datetime] = None) -> Tuple[str, str]:
    current_time = now or datetime.utcnow()
    week_start = current_time - timedelta(days=7)
    latest_login_at = _latest_login_at(db, user_id)
    has_recent_login = bool(latest_login_at and latest_login_at >= week_start)

    latest_avg_score = _overall_latest_score(db, user_id)
    low_score_mode = latest_avg_score is not None and latest_avg_score < 60
    long_gap_mode = not has_recent_login

    if long_gap_mode or low_score_mode:
        if long_gap_mode:
            return "angry", "Đang tức giận"
        return "angry", "Đang tức giận"
    return "happy", "Đang vui vẻ"


def _build_recommendation_payload(db: Session, user: models.User) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    focus_subject = _pick_focus_subject(db, user)
    if not focus_subject:
        return None, None

    # Nếu môn ưu tiên chưa có tài liệu khả dụng thì lùi sang môn có tài liệu.
    subject_map = _collect_subject_learning_map(db, user)
    ranked_subjects = [item.get("subject_name") for item in sorted(subject_map.values(), key=_focus_priority)]
    if not _has_available_documents_for_subject(db, user, focus_subject):
        for candidate in ranked_subjects:
            if isinstance(candidate, str) and _has_available_documents_for_subject(db, user, candidate):
                focus_subject = candidate
                break

    document, doc_reason = _pick_document_by_evaluation(db, user, focus_subject)
    if document is None:
        document = _pick_recommended_document(db, user, focus_subject)
        doc_reason = "Môn này đang học ít/chưa học so với các môn còn lại."

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
        "reason": f"Môn ưu tiên: {focus_subject}. Lý do tài liệu: {doc_reason}",
        "document": {
            "id": document.id,
            "filename": document.filename,
            "subject": focus_subject,
            "class_id": document.class_id,
            "summary": summary,
        },
    }
    text = (
        f"Tôi đề xuất ưu tiên môn {focus_subject}. "
        f"Tài liệu nên học trước: {document.filename}. "
        f"Lý do: {doc_reason}"
    )
    return payload, text


def _build_recommendation_payload_for_subject(db: Session, user: models.User, subject_name: str) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    forced_subject = (subject_name or "").strip()
    if not forced_subject:
        return _build_recommendation_payload(db, user)

    document, classroom = _first_available_document_for_subject(db, user, forced_subject)
    doc_reason = "Đây là tài liệu đầu tiên của lớp bạn yêu cầu mở."
    if document is None:
        document, doc_reason = _pick_document_by_evaluation(db, user, forced_subject)
        if document is None:
            document = _pick_recommended_document(db, user, forced_subject)
            doc_reason = "Đây là môn bạn yêu cầu mở trực tiếp."

    if not document:
        return {
            "subject": forced_subject,
            "reason": "Môn bạn yêu cầu hiện chưa có tài liệu khả dụng để mở.",
        }, f"Bạn yêu cầu môn {forced_subject}, nhưng hiện chưa có tài liệu khả dụng để mở."

    summary = _quick_document_summary(db, document)
    payload: Dict[str, object] = {
        "subject": forced_subject,
        "reason": f"Mở theo yêu cầu của bạn. Lý do tài liệu: {doc_reason}",
        "document": {
            "id": document.id,
            "filename": document.filename,
            "subject": forced_subject,
            "class_id": document.class_id,
            "summary": summary,
        },
    }
    text = (
        f"Đã xác nhận yêu cầu mở tài liệu môn {forced_subject}. "
        f"Tài liệu đề xuất: {document.filename}. "
        f"Lý do: {doc_reason}"
    )
    return payload, text


def _build_progress_overview_reply(db: Session, user: models.User) -> Tuple[str, Dict[str, object]]:
    progress = _build_progress_payload(db, user.id)
    subject_map = _collect_subject_learning_map(db, user)
    enrolled_classes = list(getattr(user, "enrolled_classes", []) or [])

    total_docs = 0
    pending_docs = 0
    low_score_docs = 0
    best_subject = None
    weakest_subject = None
    best_score = -1.0
    weakest_score = 101.0

    for classroom in enrolled_classes:
        docs = _available_documents_for_classroom(db, classroom)
        total_docs += len(docs)
        eval_map: Dict[int, models.StudentDocumentEvaluation] = {
            item.document_id: item
            for item in db.query(models.StudentDocumentEvaluation).filter(
                models.StudentDocumentEvaluation.user_id == user.id,
                models.StudentDocumentEvaluation.class_id == classroom.id,
            ).all()
        }
        for doc in docs:
            eval_item = eval_map.get(doc.id)
            attempts = int(getattr(eval_item, "attempts", 0) or 0)
            score = float(getattr(eval_item, "latest_score", 0.0) or 0.0)
            if attempts <= 0:
                pending_docs += 1
            elif score < 60:
                low_score_docs += 1

    for item in subject_map.values():
        latest_score = item.get("latest_score")
        if latest_score is None:
            continue
        score = float(latest_score)
        subject_name = str(item.get("subject_name") or "")
        if score > best_score:
            best_score = score
            best_subject = subject_name
        if score < weakest_score:
            weakest_score = score
            weakest_subject = subject_name

    average_score = _overall_latest_score(db, user.id)
    lines = [
        "Mình vừa xem nhanh tình hình học tập của bạn:",
        f"- Đã hoàn thành: {progress.lessons_total} bài/chủ đề đạt yêu cầu, {progress.tests_total} lần kiểm tra.",
        f"- Thời gian học tích lũy: {progress.study_minutes_total} phút (tuần này {progress.study_minutes_week} phút).",
        f"- Tài liệu cần học hiện có: {total_docs}.",
        f"- Tài liệu chưa làm bài kiểm tra: {pending_docs}.",
        f"- Tài liệu điểm thấp (<60): {low_score_docs}.",
    ]
    if average_score is not None:
        lines.append(f"- Điểm trung bình gần nhất: {average_score:.1f}.")
    if best_subject:
        lines.append(f"- Môn nổi bật nhất: {best_subject}.")
    if weakest_subject:
        lines.append(f"- Môn cần ưu tiên nhất: {weakest_subject}.")

    reply = "\n".join(lines)
    action_metadata = {
        "action_type": "open_route",
        "target": "student",
        "tab_name": "evaluation",
        "params": {
            "route": "/evaluation",
        },
        "confirm_button_text": "OK, mở tab kết quả",
        "should_auto_execute": True,
    }
    return reply, action_metadata


def _is_progress_or_plan_request(message: str) -> bool:
    text = _normalize(message)
    progress_tokens = [
        "bao nhiêu bài", "bao nhieu bai", "học bao lâu", "hoc bao lau", "bao nhiêu câu", "bao nhieu cau",
        "tiến độ", "tien do", "điểm", "diem", "score", "kết quả", "ket qua", "bao nhiêu phút", "bao nhieu phut",
    ]
    plan_tokens = [
        "kế hoạch", "ke hoach", "nên học gì", "nen hoc gi", "quên học gì", "quen hoc gi",
        "học gì tiếp", "hoc gi tiep", "đề xuất", "de xuat",
    ]
    return any(token in text for token in progress_tokens + plan_tokens)


def _is_open_document_request(message: str) -> bool:
    text = _normalize(message)
    return any(token in text for token in [
        "mở", "mo", "mở cho tôi", "mo cho toi", "mở tài liệu", "mo tai lieu", "open document", "open",
    ])


def _extract_subject_from_message(message: str, user: models.User) -> Optional[str]:
    text = _normalize(message)
    text_ascii = _normalize_ascii(message)
    for item in getattr(user, "enrolled_classes", []) or []:
        subject = (_subject_name_of_classroom(item) or "").strip()
        if not subject:
            continue
        if _normalize(subject) in text or _normalize_ascii(subject) in text_ascii:
            return subject
    return None


def _compose_flexible_learning_reply(db: Session, user: models.User) -> str:
    subject_map = _collect_subject_learning_map(db, user)
    if not subject_map:
        return "Tôi chưa đủ dữ liệu học tập theo môn để phân tích sâu. Hãy bắt đầu từ 1 tài liệu cụ thể để tôi theo dõi sát hơn."

    ranked = sorted(subject_map.values(), key=_focus_priority)
    strongest = sorted(
        subject_map.values(),
        key=lambda item: (
            -int(item.get("lessons", 0)),
            -int(item.get("tests", 0)),
            -int(item.get("study_minutes", 0)),
            -(float(item.get("latest_score", 0) or 0.0)),
        ),
    )

    weak = ranked[0] if ranked else None
    good = strongest[0] if strongest else None
    untouched = [
        item.get("subject_name")
        for item in ranked
        if int(item.get("study_minutes", 0)) == 0 and int(item.get("tests", 0)) == 0
    ]

    lines = ["Tôi vừa rà soát nhanh tình trạng học tập đa môn của bạn:"]
    if good:
        lines.append(
            f"- Môn học tốt nhất hiện tại: {good.get('subject_name')} (đã học {int(good.get('study_minutes', 0))} phút, {int(good.get('tests', 0))} lần kiểm tra)."
        )
    if weak:
        lines.append(
            f"- Môn cần ưu tiên nhất: {weak.get('subject_name')} (mức hoàn thành còn thấp: {int(weak.get('lessons', 0))} bài/chương đạt)."
        )
    if untouched:
        lines.append(f"- Môn còn nhiều nội dung chưa học: {', '.join([str(x) for x in untouched[:3] if x])}.")

    lines.append("Tôi sẽ đề xuất đúng 1 tài liệu ưu tiên để bạn mở và học ngay trong lượt này.")
    return "\n".join(lines)


def _login_gap_notice(db: Session, user_id: int, now: Optional[datetime] = None) -> Optional[str]:
    current_time = now or datetime.utcnow()
    user = db.query(models.User).filter(models.User.id == user_id).first()
    progress = db.query(models.StudentLearningProgress).filter(models.StudentLearningProgress.user_id == user_id).first()
    if not progress and not user:
        return "Orbit chưa có dữ liệu đăng nhập gần nhất của bạn. Hãy đăng nhập thường xuyên hơn để tôi theo dõi sát hơn."

    previous_login = None
    if progress:
        previous_login = progress.previous_login_at or progress.last_login_at
    if not previous_login and user:
        previous_login = user.last_login_at

    if not previous_login:
        return "Đây là lần đầu bạn đăng nhập vào hệ thống học. Bắt đầu học đều ngay từ hôm nay nhé."

    gap_days = (current_time - previous_login).days
    if gap_days <= 0:
        return "Lần đăng nhập trước của bạn là trong hôm nay. Tiếp tục giữ nhịp đăng nhập thường xuyên để không trễ tiến độ."
    if gap_days == 1:
        return "Lần đăng nhập trước là 1 ngày trước. Ổn, nhưng bạn vẫn nên vào hệ thống đều mỗi ngày để giữ đà học tập."
    if gap_days < 7:
        return f"Bạn đã {gap_days} ngày chưa đăng nhập. Orbit nhắc bạn cần vào hệ thống thường xuyên hơn để giữ nhịp học."
    return f"⚠️ Bạn đã {gap_days} ngày chưa đăng nhập. Orbit cảnh báo: khoảng nghỉ này quá dài, cần học lại ngay hôm nay để tránh tụt tiến độ."


def _last_study_notice(db: Session, user_id: int, now: Optional[datetime] = None) -> str:
    current_time = now or datetime.utcnow()
    last_session = db.query(models.StudySession).filter(
        models.StudySession.user_id == user_id
    ).order_by(models.StudySession.start_time.desc()).first()

    if not last_session or not last_session.start_time:
        return "Orbit chưa ghi nhận buổi học nào trước đó của bạn. Hãy bắt đầu 1 buổi học ngay bây giờ."

    gap_days = (current_time - last_session.start_time).days
    if gap_days <= 0:
        return "Lần học bài gần nhất: hôm nay. Nhịp học tốt, tiếp tục duy trì."
    if gap_days == 1:
        return "Lần học bài gần nhất: 1 ngày trước. Bạn nên học tiếp trong hôm nay để giữ nhịp."
    if gap_days < 7:
        return f"Lần học bài gần nhất: {gap_days} ngày trước. Bạn cần học lại sớm để không quên kiến thức."
    return f"⚠️ Lần học bài gần nhất: {gap_days} ngày trước. Orbit nhắc nghiêm: đã nghỉ quá lâu, cần quay lại học ngay."


def _last_work_session_notice(db: Session, user_id: int, now: Optional[datetime] = None) -> str:
    current_time = now or datetime.utcnow()
    latest_study = db.query(models.StudySession).filter(
        models.StudySession.user_id == user_id
    ).order_by(models.StudySession.start_time.desc()).first()
    latest_login = db.query(models.UserLoginSession).filter(
        models.UserLoginSession.user_id == user_id
    ).order_by(models.UserLoginSession.login_at.desc()).first()

    candidates: List[datetime] = []
    if latest_study and latest_study.start_time:
        candidates.append(latest_study.start_time)
    if latest_login and latest_login.login_at:
        candidates.append(latest_login.login_at)

    if not candidates:
        return "Orbit chưa ghi nhận phiên làm việc nào trước đó của bạn."

    last_time = max(candidates)
    gap_days = (current_time - last_time).days
    if gap_days <= 0:
        return "Phiên làm việc gần nhất: hôm nay."
    if gap_days == 1:
        return "Phiên làm việc gần nhất: 1 ngày trước."
    return f"Phiên làm việc gần nhất: {gap_days} ngày trước."


def _get_or_create_orbit_session(db: Session, user_id: int, class_id: Optional[int], subject_id: Optional[int], requested_session_id: Optional[int] = None) -> models.OrbitChatSession:
    now = datetime.utcnow()

    if requested_session_id:
        existing = db.query(models.OrbitChatSession).filter(
            models.OrbitChatSession.id == requested_session_id,
            models.OrbitChatSession.user_id == user_id,
        ).first()
        if existing:
            if class_id and not existing.class_id:
                existing.class_id = class_id
            if subject_id and not existing.subject_id:
                existing.subject_id = subject_id
            return existing

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


def _get_recent_orbit_messages(db: Session, user_id: int, session_id: Optional[int] = None, limit: int = 40):
    target_session = None
    if session_id:
        target_session = db.query(models.OrbitChatSession).filter(
            models.OrbitChatSession.id == session_id,
            models.OrbitChatSession.user_id == user_id,
        ).first()
    if target_session is None:
        target_session = db.query(models.OrbitChatSession).filter(
            models.OrbitChatSession.user_id == user_id,
        ).order_by(models.OrbitChatSession.last_message_at.desc()).first()

    if target_session is None:
        return None, []

    rows = db.query(models.OrbitChatMessage).filter(
        models.OrbitChatMessage.user_id == user_id,
        models.OrbitChatMessage.session_id == target_session.id,
    ).order_by(models.OrbitChatMessage.created_at.asc()).all()

    payload = [
        {
            "role": item.role,
            "content": item.content,
            "created_at": (item.created_at or datetime.utcnow()).isoformat(),
        }
        for item in rows[-limit:]
    ]
    return target_session.id, payload


def _sync_learning_progress(db: Session, user_id: int):
    now = datetime.utcnow()

    total_lessons = db.query(models.StudentDocumentEvaluation).filter(
        models.StudentDocumentEvaluation.user_id == user_id,
        models.StudentDocumentEvaluation.is_completed == True,
    ).count()

    total_tests = db.query(models.StudentDocumentScoreHistory).filter(
        models.StudentDocumentScoreHistory.user_id == user_id,
        models.StudentDocumentScoreHistory.test_type != "baseline",
    ).count()
    total_study = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(models.StudySession.user_id == user_id).all())
    total_login_seconds = sum(int(item.duration_seconds or 0) for item in db.query(models.UserLoginSession).filter(models.UserLoginSession.user_id == user_id).all())
    total_login_minutes = int(total_login_seconds // 60)

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
    progress.total_study_minutes = int(total_study + total_login_minutes)
    progress.total_agent_messages = int(total_msgs)
    progress.total_agent_chat_seconds = int(total_chat_sec)
    progress.last_active_at = now


def _build_progress_payload(db: Session, user_id: int) -> OrbitProgressResponse:
    now = datetime.utcnow()
    week_start, _ = _week_bounds(now)
    month_start = _month_start(now)

    lessons_total = db.query(models.StudentDocumentEvaluation).filter(
        models.StudentDocumentEvaluation.user_id == user_id,
        models.StudentDocumentEvaluation.is_completed == True,
    ).count()

    lesson_attempts_week = db.query(models.StudentDocumentScoreHistory).filter(
        models.StudentDocumentScoreHistory.user_id == user_id,
        models.StudentDocumentScoreHistory.score >= 60,
        models.StudentDocumentScoreHistory.test_type != "baseline",
        models.StudentDocumentScoreHistory.tested_at >= week_start,
    ).all()
    lessons_week = len({item.document_id for item in lesson_attempts_week})

    lesson_attempts_month = db.query(models.StudentDocumentScoreHistory).filter(
        models.StudentDocumentScoreHistory.user_id == user_id,
        models.StudentDocumentScoreHistory.score >= 60,
        models.StudentDocumentScoreHistory.test_type != "baseline",
        models.StudentDocumentScoreHistory.tested_at >= month_start,
    ).all()
    lessons_month = len({item.document_id for item in lesson_attempts_month})

    study_total = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(models.StudySession.user_id == user_id).all())
    study_week = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(
        models.StudySession.user_id == user_id,
        models.StudySession.start_time >= week_start,
    ).all())
    study_month = sum(int(item.duration_minutes or 0) for item in db.query(models.StudySession).filter(
        models.StudySession.user_id == user_id,
        models.StudySession.start_time >= month_start,
    ).all())

    login_total_minutes = int(sum(int(item.duration_seconds or 0) for item in db.query(models.UserLoginSession).filter(
        models.UserLoginSession.user_id == user_id,
    ).all()) // 60)
    login_week_minutes = int(sum(int(item.duration_seconds or 0) for item in db.query(models.UserLoginSession).filter(
        models.UserLoginSession.user_id == user_id,
        models.UserLoginSession.login_at >= week_start,
    ).all()) // 60)
    login_month_minutes = int(sum(int(item.duration_seconds or 0) for item in db.query(models.UserLoginSession).filter(
        models.UserLoginSession.user_id == user_id,
        models.UserLoginSession.login_at >= month_start,
    ).all()) // 60)

    study_total += login_total_minutes
    study_week += login_week_minutes
    study_month += login_month_minutes

    tests_total = db.query(models.StudentDocumentScoreHistory).filter(
        models.StudentDocumentScoreHistory.user_id == user_id,
        models.StudentDocumentScoreHistory.test_type != "baseline",
    ).count()
    tests_week = db.query(models.StudentDocumentScoreHistory).filter(
        models.StudentDocumentScoreHistory.user_id == user_id,
        models.StudentDocumentScoreHistory.test_type != "baseline",
        models.StudentDocumentScoreHistory.tested_at >= week_start,
    ).count()
    tests_month = db.query(models.StudentDocumentScoreHistory).filter(
        models.StudentDocumentScoreHistory.user_id == user_id,
        models.StudentDocumentScoreHistory.test_type != "baseline",
        models.StudentDocumentScoreHistory.tested_at >= month_start,
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


@router.get("/weekly-inactivity")
def get_weekly_inactivity_report(
    teacher_id: Optional[int] = None,
    class_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return build_weekly_inactivity_report(db, teacher_id=teacher_id, class_id=class_id)


@router.post("/weekly-reminders/send")
def trigger_weekly_reminders(
    teacher_id: Optional[int] = None,
    class_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return send_weekly_reminders(db, teacher_id=teacher_id, class_id=class_id)


@router.post("/chat")
def chat_with_orbit(req: OrbitChatRequest, db: Session = Depends(get_db)):
    logger.info(
        "orbit_chat start user_id=%s subject=%s class_id=%s document_id=%s source_file=%s session_id=%s message=%s",
        req.user_id,
        req.subject,
        req.class_id,
        req.document_id,
        req.source_file,
        req.session_id,
        (req.message or "")[:200],
    )
    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Orbit chỉ dành cho tài khoản sinh viên")

    enrolled_classes = list(getattr(user, "enrolled_classes", []) or [])
    is_entry = _is_entry_message(req.message)
    requested_subject = (req.subject or "").strip()

    subject_name = requested_subject
    classroom = None
    if req.class_id:
        classroom = db.query(models.Classroom).filter(models.Classroom.id == req.class_id).first()

    if classroom is None and not _is_all_subject(subject_name):
        classroom = next(
            (item for item in enrolled_classes if _normalize(item.subject or "") == _normalize(subject_name)),
            None,
        )

    if classroom is None and enrolled_classes:
        classroom = enrolled_classes[0]

    if classroom is not None:
        subject_name = (classroom.subject or getattr(getattr(classroom, "subject_obj", None), "name", None) or subject_name or "").strip()

    subject = None
    if subject_name:
        subject = db.query(models.Subject).filter(models.Subject.name.ilike(subject_name)).first()
        if not subject and not _is_all_subject(subject_name):
            subject = models.Subject(name=subject_name, description=f"Môn {subject_name}")
            db.add(subject)
            db.flush()

    selected_doc = _resolve_selected_document(
        db=db,
        user=user,
        classroom=classroom,
        document_id=req.document_id,
        source_file=req.source_file,
    )
    if selected_doc is not None:
        logger.info(
            "orbit_chat selected_document_direct doc_id=%s filename=%s class_id=%s subject=%s",
            selected_doc.id,
            selected_doc.filename,
            selected_doc.class_id,
            selected_doc.subject,
        )
    if selected_doc is not None:
        matched_classroom = next(
            (item for item in enrolled_classes if item.id == selected_doc.class_id),
            None,
        )
        if matched_classroom is not None:
            classroom = matched_classroom
        subject_name = (
            getattr(getattr(selected_doc, "subject_obj", None), "name", None)
            or selected_doc.subject
            or subject_name
            or ""
        ).strip()
        if getattr(selected_doc, "subject_id", None):
            subject = db.query(models.Subject).filter(models.Subject.id == selected_doc.subject_id).first() or subject

    orbit_mode, orbit_status_text = _entry_orbit_mode(db, user.id)
    login_notice = _login_gap_notice(db, user.id)
    study_notice = _last_study_notice(db, user.id)
    work_notice = _last_work_session_notice(db, user.id)
    progress = _build_progress_payload(db, user.id)

    if _is_progress_overview_request(req.message):
        reply, action_metadata = _build_progress_overview_reply(db, user)
        now = datetime.utcnow()
        session = _get_or_create_orbit_session(
            db,
            user.id,
            classroom.id if classroom else None,
            subject.id if subject else None,
            requested_session_id=req.session_id,
        )

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
            "class_id": classroom.id if classroom else None,
            "subject": subject_name or "all",
            "recommendation": None,
            "action_metadata": action_metadata,
            "orbit_mode": orbit_mode,
            "orbit_status_text": orbit_status_text,
            "quick_suggestions": [
                "Hôm nay, tôi nên học phần nào",
                "Thành tích học của tôi thế nào",
                "Mở cho tôi tài liệu môn Lập trình hướng đối tượng",
            ],
            "session_id": session.id,
            "debug_version": "orbit_patch_v3",
        }

    if classroom is None:
        intro_lines = [
            "Xin chào, mình là Orbit Agent - trợ lý học tập cá nhân của bạn.",
            ("😠 Orbit Angry đang làm việc." if orbit_mode == "angry" else "😊 Orbit Happy đang sẵn sàng đồng hành cùng bạn."),
            f"- {work_notice}",
            f"- {login_notice}",
            f"- {study_notice}",
            f"- Tiến độ hiện tại: {progress.lessons_total} bài đã qua, {progress.tests_total} bài kiểm tra.",
            f"- Thời lượng học: tuần này {progress.study_minutes_week} phút, tháng này {progress.study_minutes_month} phút, tổng {progress.study_minutes_total} phút.",
            "Bạn chưa join lớp nào. Hãy tham gia ít nhất 1 lớp để bắt đầu hành trình học cùng Orbit và nhận đề xuất tài liệu phù hợp.",
        ]
        reply = "\n".join(intro_lines)
        return {
            "reply": reply,
            "agent_name": "Orbit Agent",
            "class_id": None,
            "subject": subject_name or "all",
            "recommendation": None,
            "action_metadata": None,
            "orbit_mode": orbit_mode,
            "orbit_status_text": orbit_status_text,
        }

    if selected_doc is None:
        selected_doc = _resolve_selected_document(
            db=db,
            user=user,
            classroom=classroom,
            document_id=req.document_id,
            source_file=req.source_file,
        )
    potential_document_context_request = bool((req.message or "").strip()) and not any([
        is_entry,
        _is_open_document_request(req.message),
        _is_progress_or_plan_request(req.message),
        _should_recommend_study(req.message),
        _is_progress_overview_request(req.message),
    ])
    if selected_doc is None and potential_document_context_request:
        selected_doc = _recover_selected_document_from_history(
            db=db,
            user=user,
            classroom=classroom,
            session_id=req.session_id,
        )
        if selected_doc is not None:
            logger.info(
                "orbit_chat selected_document_from_history doc_id=%s filename=%s session_id=%s",
                selected_doc.id,
                selected_doc.filename,
                req.session_id,
            )
    if selected_doc is not None and selected_doc.class_id:
        matched_classroom = next(
            (item for item in enrolled_classes if item.id == selected_doc.class_id),
            None,
        )
        if matched_classroom is not None:
            classroom = matched_classroom
            subject_name = (
                getattr(getattr(selected_doc, "subject_obj", None), "name", None)
                or selected_doc.subject
                or subject_name
                or ""
            ).strip()
    document_context_request = _is_document_learning_request(req.message, selected_doc)
    logger.info(
        "orbit_chat routing subject=%s classroom_id=%s selected_doc_id=%s is_entry=%s document_context_request=%s",
        subject_name,
        classroom.id if classroom else None,
        selected_doc.id if selected_doc else None,
        is_entry,
        document_context_request,
    )

    orbit = OrbitAgent(db)
    if is_entry:
        reply = ""
    elif document_context_request and selected_doc is not None:
        logger.info(
            "orbit_chat branch=document_context doc_id=%s filename=%s",
            selected_doc.id,
            selected_doc.filename,
        )
        doc_subject_name = (
            getattr(getattr(selected_doc, "subject_obj", None), "name", None)
            or selected_doc.subject
            or subject_name
            or ""
        ).strip()
        reply = _reply_with_open_document_context(
            db=db,
            user=user,
            classroom=classroom,
            subject_name=doc_subject_name,
            selected_doc=selected_doc,
            message=req.message,
            session_id=req.session_id,
        )
        if not reply:
            reply = "Tôi đang bám vào tài liệu đang mở nhưng chưa rút ra được câu trả lời rõ ràng. Bạn hãy hỏi cụ thể hơn theo đúng phần tài liệu này."
    else:
        logger.info("orbit_chat branch=generic_advice")
        # Ưu tiên phản hồi thích ứng đa môn để tránh lặp mẫu câu mặc định của OrbitAgent.
        if _is_summary_request(req.message):
            reply = orbit.respond(user=user, subject_name=subject_name, message=req.message, class_id=classroom.id)
        else:
            reply = _compose_flexible_learning_reply(db, user)

    if is_entry:
        mood_line = "😠 Orbit Angry đang làm việc." if orbit_mode == "angry" else "😊 Orbit Happy chào bạn quay lại học tập."
        header_lines = [
            "Xin chào, mình là Orbit Agent - trợ lý học tập cá nhân của bạn.",
            "📌 Orbit báo cáo nhanh khi bạn vừa vào hệ thống:",
            mood_line,
            f"- {work_notice}",
            f"- {login_notice}",
            f"- {study_notice}",
            f"- Tiến độ hiện tại: {progress.lessons_total} bài đã qua, {progress.tests_total} bài kiểm tra.",
            f"- Thời lượng học: tuần này {progress.study_minutes_week} phút, tháng này {progress.study_minutes_month} phút, tổng {progress.study_minutes_total} phút.",
        ]
        reply = "\n".join(header_lines)

    recommendation_payload: Optional[Dict[str, object]] = None
    action_metadata: Optional[Dict[str, object]] = None

    requested_subject_from_msg = _extract_subject_from_message(req.message, user) if _is_open_document_request(req.message) else None
    should_recommend = (
        is_entry
        or _should_recommend_study(req.message)
        or (_is_open_document_request(req.message) and not document_context_request)
        or (
            not document_context_request
            and not _is_progress_or_plan_request(req.message)
            and not _is_summary_request(req.message)
        )
    )

    if should_recommend:
        if requested_subject_from_msg:
            recommendation_payload, recommendation_text = _build_recommendation_payload_for_subject(db, user, requested_subject_from_msg)
        else:
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
                "confirm_button_text": "OK, mở tài liệu đề xuất",
                "should_auto_execute": False,
            }
    elif _is_open_document_request(req.message) and not document_context_request:
        if requested_subject_from_msg:
            recommendation_payload, recommendation_text = _build_recommendation_payload_for_subject(db, user, requested_subject_from_msg)
        else:
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
                "confirm_button_text": "OK, mở tài liệu này",
                "should_auto_execute": False,
            }

    if _is_summary_request(req.message) and not document_context_request:
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
    session = _get_or_create_orbit_session(
        db,
        user.id,
        classroom.id,
        subject.id if subject else None,
        requested_session_id=req.session_id,
    )

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
    logger.info(
        "orbit_chat done session_id=%s class_id=%s subject=%s action_type=%s recommendation_doc_id=%s",
        session.id,
        classroom.id,
        subject_name,
        (action_metadata or {}).get("action_type") if action_metadata else None,
        ((recommendation_payload or {}).get("document") or {}).get("id")
        if isinstance(recommendation_payload, dict)
        else None,
    )

    return {
        "reply": reply,
        "agent_name": "Orbit Agent",
        "class_id": classroom.id,
        "subject": subject_name,
        "recommendation": recommendation_payload,
        "action_metadata": action_metadata,
        "orbit_mode": orbit_mode,
        "orbit_status_text": orbit_status_text,
        "quick_suggestions": [
            "Hôm nay, tôi nên học phần nào",
            "Thành tích học của tôi thế nào",
            "Mở cho tôi tài liệu môn Lập trình hướng đối tượng",
        ],
        "session_id": session.id,
        "debug_version": "orbit_patch_v4",
    }


@router.get("/history/{user_id}", response_model=OrbitHistoryResponse)
def get_orbit_history(
    user_id: int,
    session_id: Optional[int] = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Orbit chỉ dành cho tài khoản sinh viên")

    sid, messages = _get_recent_orbit_messages(db, user_id, session_id=session_id, limit=limit)
    return {
        "session_id": sid,
        "messages": messages,
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
