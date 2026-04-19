from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.teacher_agent import TeacherAgent
from db.database import get_db
from db.models import Classroom, Subject, User
from memory.conversation_memory import get_conversation_memory
from memory.intent_classifier import IntentClassifier

router = APIRouter()


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

    pending_request = memory.get_pending_request(teacher_id, class_id)
    intent_type = analysis["intent_type"]
    entities = analysis["entities"]
    if pending_request and (analysis["needs_follow_up"] or analysis["confidence"] < 0.4 or intent_type == agent.classifier.GENERAL_QUESTION):
        intent_type = pending_request.get("intent_type", intent_type)
        entities = agent._merge_pending_entities(pending_request, entities)

    explicit_subject = agent._find_subject_in_message(message)
    subject = explicit_subject or agent._resolve_subject(entities, context)

    explicit_classroom = agent._find_classroom_in_message(message, subject)
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
        result = agent._material_reply(subject, classroom, message)
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
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập yêu cầu cho agent")

    try:
        agent = TeacherAgent(db)
        return agent.respond(
            teacher_id=req.teacher_id,
            class_id=req.class_id,
            message=req.message.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể xử lý yêu cầu của giảng viên: {str(exc)}")


@router.post("/nova-interactive")
def nova_interactive(req: NovaInteractiveRequest, db: Session = Depends(get_db)):
    """
    Endpoint cho Nova Agent interactive:
    - Phân loại ý định người dùng
    - Quản lý conversation memory
    - Định tuyến sang các UI component phù hợp
    - Trả về action metadata cho frontend
    """
    print(f"[NOVA] Request received: teacher_id={req.teacher_id}, class_id={req.class_id}, message='{req.message[:50]}'")
    
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập yêu cầu cho agent")

    try:
        agent = TeacherAgent(db)
        agent_response = agent.respond(
            teacher_id=req.teacher_id,
            class_id=req.class_id,
            message=req.message.strip(),
        )
        return {
            **agent_response,
        }
        
    except ValueError as exc:
        print(f"[NOVA] ValueError: {exc}")
        raise HTTPException(status_code=403, detail=str(exc))
    except NameError as exc:
        if "histories" in str(exc):
            print(f"[NOVA] NameError fallback triggered: {exc}")
            agent = TeacherAgent(db)
            try:
                return _build_nova_fallback_response(agent, req.teacher_id, req.class_id, req.message.strip())
            except Exception as fallback_exc:
                print(f"[NOVA] Fallback failed: {type(fallback_exc).__name__}: {fallback_exc}")
                import traceback
                traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Nova error: {str(exc)}")
    except Exception as exc:
        print(f"[NOVA] Exception: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Nova error: {str(exc)}")