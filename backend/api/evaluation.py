from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.evaluation_agent import EvaluationAgent
from db import models
from db.database import get_db

router = APIRouter()


class EvaluationChatRequest(BaseModel):
    user_id: int
    message: str
    subject: Optional[str] = None


@router.post("/chat")
def evaluation_chat(req: EvaluationChatRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Chỉ tài khoản sinh viên mới được dùng Evaluation Agent")
    if not (req.message or "").strip():
        raise HTTPException(status_code=400, detail="Nội dung chat không được để trống")

    agent = EvaluationAgent(db)
    reply = agent.chat_about_progress(
        user_id=req.user_id,
        message=req.message,
        subject=req.subject,
    )
    return {"ok": True, "reply": reply}


@router.get("/chat/examples")
def evaluation_chat_examples():
    return {
        "examples": [
            "Thành tích học tập của tôi hiện nay thế nào?",
            "Môn nào tôi đang yếu nhất?",
            "Tôi có tiến bộ hơn trong 2 tuần gần đây không?",
            "Tài liệu nào tôi nên ôn tập lại trước kỳ thi?",
        ]
    }
