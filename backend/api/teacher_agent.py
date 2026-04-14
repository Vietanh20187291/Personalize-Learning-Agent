from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.teacher_agent import TeacherAgent
from db.database import get_db

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
    except Exception as exc:
        print(f"[NOVA] Exception: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Nova error: {str(exc)}")