import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.teacher_agent import TeacherAgent
from db.database import get_db
from db.models import Classroom, Subject, User
from logging_config import error_json_response
from memory.conversation_memory import get_conversation_memory
from memory.intent_classifier import IntentClassifier

router = APIRouter()
logger = logging.getLogger("app.nova")


class TeacherAssistantRequest(BaseModel):
    teacher_id: int
    class_id: int
    message: str


class NovaInteractiveRequest(BaseModel):
    """Request model cho Nova Agent interactive"""
    teacher_id: int
    class_id: int
    message: str


def _build_nova_fallback_response(agent: TeacherAgent, teacher_id: int, class_id: int, message: str):
    memory = get_conversation_memory()
    context = memory.get_context(teacher_id, class_id)
    analysis = agent.classifier.classify_request(message, context)
    canonical_message = agent._clean_text(analysis.get("rewritten_message") or message)

    pending_request = memory.get_pending_request(teacher_id, class_id)
    intent_type = analysis["intent_type"]
    entities = analysis["entities"]
    if pending_request and (analysis["needs_follow_up"] or analysis["confidence"] < 0.4 or intent_type == agent.classifier.GENERAL_QUESTION):
        intent_type = pending_request.get("intent_type", intent_type)
        entities = agent._merge_pending_entities(pending_request, entities)

    explicit_subject = agent._find_subject_in_message(canonical_message, entities=entities)
    subject = explicit_subject or agent._resolve_subject(entities, context)

    explicit_classroom = agent._find_classroom_in_message(canonical_message, subject, entities=entities)
    classroom = explicit_classroom or agent._resolve_classroom(entities, context, subject)
    student = agent._resolve_student(entities, context, classroom)

    if not subject and classroom:
        subject = agent._resolve_subject({"subject_name": classroom.subject or getattr(classroom.subject_obj, "name", "")}, context, classroom)

    if intent_type == IntentClassifier.COURSE_INFO and subject is not None:
        result = agent._course_info_reply(subject)
    elif intent_type == IntentClassifier.CLASS_OVERVIEW:
        classroom = classroom or agent.db.query(Classroom).filter(Classroom.id == class_id).first()
        if classroom is None:
            result = {"reply": "Không tìm thấy lớp học.", "suggested_actions": ["Chọn lại lớp học", "Kiểm tra mã lớp"]}
        else:
            subject = subject or agent._resolve_subject({"subject_name": classroom.subject or getattr(classroom.subject_obj, "name", "")}, context, classroom)
            result = agent._class_overview_reply(classroom, subject, context)
    elif intent_type == IntentClassifier.CLASS_ANALYTICS:
        if classroom is not None:
            subject = subject or agent._resolve_subject({"subject_name": classroom.subject or getattr(classroom.subject_obj, "name", "")}, context, classroom)
            result = agent._class_analytics_reply(classroom, subject)
        else:
            result = agent._class_analytics_reply(None, subject)
    elif intent_type == IntentClassifier.STUDENT_INFO and student is not None:
        result = agent._student_overview_reply(student)
    elif intent_type == IntentClassifier.MATERIAL:
        result = agent._material_reply(subject, classroom, canonical_message)
    elif intent_type == IntentClassifier.EXAM_GENERATION and subject is not None:
        exam_type = entities.get("exam_type") or "multiple_choice"
        num_questions = int(entities.get("num_questions") or 0)
        num_versions = int(entities.get("num_versions") or 0)
        difficulty = entities.get("difficulty")
        result = agent._generate_exam_versions(subject, exam_type, num_questions, num_versions, difficulty=difficulty)
    else:
        result = agent._build_general_reply(subject, classroom)

    response_intent = intent_type
    result["class_name"] = classroom.name if classroom else result.get("class_name", "")
    result["subject"] = subject.name if subject else result.get("subject", "")
    result["intent_type"] = response_intent
    result["confidence"] = analysis["confidence"]
    result["action_metadata"] = agent.router.route_action(
        response_intent,
        context=context,
        class_id=classroom.id if classroom else class_id,
        student_name=agent._clean_text(student.full_name or student.username) if student else None,
        subject_name=subject.name if subject else None,
    )
    return result


@router.post("/assistant")
def teacher_assistant(req: TeacherAssistantRequest, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        if not req.message or not req.message.strip():
            raise HTTPException(status_code=400, detail="Vui lòng nhập yêu cầu cho agent")

        logger.info(
            "teacher_assistant start teacher_id=%s class_id=%s message=%s",
            req.teacher_id,
            req.class_id,
            (req.message or "")[:200],
        )
        agent = TeacherAgent(db)
        response = agent.respond(
            teacher_id=req.teacher_id,
            class_id=req.class_id,
            message=req.message.strip(),
        )
        logger.info(
            "teacher_assistant done teacher_id=%s class_id=%s duration_ms=%s",
            req.teacher_id,
            req.class_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return response
    except HTTPException as exc:
        logger.warning(
            "teacher_assistant rejected teacher_id=%s class_id=%s status=%s duration_ms=%s detail=%s",
            req.teacher_id,
            req.class_id,
            exc.status_code,
            round((time.perf_counter() - started) * 1000, 2),
            exc.detail,
        )
        return error_json_response(exc.status_code, str(exc.detail), retryable=exc.status_code >= 500)
    except Exception:
        logger.exception(
            "teacher_assistant failed teacher_id=%s class_id=%s duration_ms=%s",
            req.teacher_id,
            req.class_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return error_json_response(
            500,
            "Nova tạm thời chưa thể xử lý yêu cầu này. Vui lòng thử lại sau ít phút.",
            retryable=True,
        )


@router.post("/nova-interactive")
def nova_interactive(req: NovaInteractiveRequest, db: Session = Depends(get_db)):
    """
    Endpoint cho Nova Agent interactive:
    - Phân loại ý định người dùng
    - Quản lý conversation memory
    - Định tuyến sang các UI component phù hợp
    - Trả về action metadata cho frontend
    """
    started = time.perf_counter()
    try:
        if not req.message or not req.message.strip():
            raise HTTPException(status_code=400, detail="Vui lòng nhập yêu cầu cho agent")

        logger.info(
            "nova_interactive start teacher_id=%s class_id=%s message=%s",
            req.teacher_id,
            req.class_id,
            (req.message or "")[:200],
        )
        agent = TeacherAgent(db)
        agent_response = agent.respond(
            teacher_id=req.teacher_id,
            class_id=req.class_id,
            message=req.message.strip(),
        )
        logger.info(
            "nova_interactive done teacher_id=%s class_id=%s duration_ms=%s",
            req.teacher_id,
            req.class_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return {
            **agent_response,
        }
    except HTTPException as exc:
        logger.warning(
            "nova_interactive rejected teacher_id=%s class_id=%s status=%s duration_ms=%s detail=%s",
            req.teacher_id,
            req.class_id,
            exc.status_code,
            round((time.perf_counter() - started) * 1000, 2),
            exc.detail,
        )
        return error_json_response(exc.status_code, str(exc.detail), retryable=exc.status_code >= 500)
    except ValueError as exc:
        logger.warning(
            "nova_interactive value_error teacher_id=%s class_id=%s duration_ms=%s detail=%s",
            req.teacher_id,
            req.class_id,
            round((time.perf_counter() - started) * 1000, 2),
            exc,
        )
        return error_json_response(403, str(exc), retryable=False)
    except NameError as exc:
        if "histories" in str(exc):
            logger.warning(
                "nova_interactive fallback teacher_id=%s class_id=%s duration_ms=%s detail=%s",
                req.teacher_id,
                req.class_id,
                round((time.perf_counter() - started) * 1000, 2),
                exc,
            )
            agent = TeacherAgent(db)
            try:
                response = _build_nova_fallback_response(agent, req.teacher_id, req.class_id, req.message.strip())
                logger.info(
                    "nova_interactive fallback_done teacher_id=%s class_id=%s duration_ms=%s",
                    req.teacher_id,
                    req.class_id,
                    round((time.perf_counter() - started) * 1000, 2),
                )
                return response
            except Exception:
                logger.exception(
                    "nova_interactive fallback_failed teacher_id=%s class_id=%s duration_ms=%s",
                    req.teacher_id,
                    req.class_id,
                    round((time.perf_counter() - started) * 1000, 2),
                )
        logger.exception(
            "nova_interactive name_error teacher_id=%s class_id=%s duration_ms=%s",
            req.teacher_id,
            req.class_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return error_json_response(
            500,
            "Nova gặp lỗi nội bộ khi xử lý yêu cầu. Vui lòng thử lại sau ít phút.",
            retryable=True,
        )
    except Exception:
        logger.exception(
            "nova_interactive failed teacher_id=%s class_id=%s duration_ms=%s",
            req.teacher_id,
            req.class_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return error_json_response(
            500,
            "Nova tạm thời chưa thể xử lý yêu cầu này. Vui lòng thử lại sau ít phút.",
            retryable=True,
        )
