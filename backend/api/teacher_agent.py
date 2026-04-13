from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.teacher_agent import TeacherAgent
from db.database import get_db
from memory import get_conversation_memory, IntentClassifier, ActionRouter

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
        # 1. Lấy conversation memory
        memory = get_conversation_memory()
        context = memory.get_context(req.teacher_id, req.class_id)
        
        # 2. Phân loại ý định
        classifier = IntentClassifier()
        intent_type, confidence, matched_keywords = classifier.classify(req.message.strip(), context)
        
        # 3. Lưu message vào history
        memory.add_message(
            req.teacher_id,
            req.class_id,
            "user",
            req.message.strip(),
            {"intent": intent_type, "confidence": confidence}
        )
        
        # 4. Định tuyến hành động
        router = ActionRouter()
        action_metadata = router.route_action(
            intent_type=intent_type,
            context=context,
            class_id=req.class_id,
            student_name=classifier.extract_names(req.message.strip())[0] if classifier.extract_names(req.message.strip()) else None
        )
        
        # 5. Gọi TeacherAgent để lấy reply chuyên sâu
        agent = TeacherAgent(db)
        agent_response = agent.respond(
            teacher_id=req.teacher_id,
            class_id=req.class_id,
            message=req.message.strip(),
        )
        
        # 6. Ghi vào memory
        memory.add_message(
            req.teacher_id,
            req.class_id,
            "agent",
            agent_response.get("reply", ""),
            {"action_metadata": action_metadata}
        )
        
        # 7. Cập nhật context
        context_updates = {
            "last_action_type": intent_type,
        }
        if classifier.extract_names(req.message.strip()):
            context_updates["last_student_asked"] = {
                "name": classifier.extract_names(req.message.strip())[0]
            }
        memory.update_context(req.teacher_id, req.class_id, context_updates)
        
        # 8. Trả về response kết hợp
        return {
            "reply": agent_response.get("reply", ""),
            "suggested_actions": agent_response.get("suggested_actions", []),
            "class_name": agent_response.get("class_name", ""),
            "subject": agent_response.get("subject", ""),
            "action_metadata": action_metadata,  # Metadata cho frontend
            "intent_type": intent_type,
            "confidence": confidence,
        }
        
    except ValueError as exc:
        print(f"[NOVA] ValueError: {exc}")
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        print(f"[NOVA] Exception: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Nova error: {str(exc)}")