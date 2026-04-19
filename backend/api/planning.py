from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.planning_agent import PlanningAgent
from db import models
from db.database import get_db


router = APIRouter()


class RegeneratePlanRequest(BaseModel):
    user_id: int
    reason: Optional[str] = "manual"


class PlanningChatRequest(BaseModel):
    user_id: int
    message: str


@router.get("/plan/{user_id}")
def get_student_plan(user_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    if user.role != "student":
        raise HTTPException(status_code=403, detail="Chỉ tài khoản sinh viên mới có kế hoạch học tập")

    agent = PlanningAgent(db)
    if refresh:
        plan = agent.regenerate_for_user(
            user_id=user_id,
            reason="manual_refresh",
            reference_login_at=datetime.utcnow(),
        )
    else:
        plan = agent.get_active_plan(user_id=user_id)

    return {"ok": True, "plan": plan}


@router.post("/plan/regenerate")
def regenerate_plan(req: RegeneratePlanRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    if user.role != "student":
        raise HTTPException(status_code=403, detail="Chỉ tài khoản sinh viên mới có kế hoạch học tập")

    agent = PlanningAgent(db)
    plan = agent.regenerate_for_user(
        user_id=req.user_id,
        reason=req.reason or "manual",
        reference_login_at=datetime.utcnow(),
    )
    return {"ok": True, "message": "Đã tạo lại kế hoạch học tập.", "plan": plan}


@router.post("/chat")
def planning_chat(req: PlanningChatRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    if user.role != "student":
        raise HTTPException(status_code=403, detail="Chỉ tài khoản sinh viên mới có kế hoạch học tập")

    if not (req.message or "").strip():
        raise HTTPException(status_code=400, detail="Nội dung chat không được để trống")

    agent = PlanningAgent(db)
    result = agent.apply_plan_adjustment(user_id=req.user_id, message=req.message)
    return {
        "ok": True,
        "reply": result.get("message", "Đã cập nhật kế hoạch học tập."),
        "plan": result.get("plan", {}),
    }


@router.get("/chat/examples")
def planning_chat_examples():
    return {
        "examples": [
            "Đẩy các tài liệu môn Lập trình hướng đối tượng lên học trước",
            "Đưa các tài liệu môn Lưu trữ và phân tích dữ liệu ra học sau",
            "Thêm 2 tài liệu học cho hôm nay",
            "Thêm 2 tài liệu học cho tuần này",
        ]
    }
