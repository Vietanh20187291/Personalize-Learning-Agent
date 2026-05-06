import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.planning_agent import PlanningAgent
from db import models
from db.database import get_db
from logging_config import error_json_response


router = APIRouter()
logger = logging.getLogger("app.planning")


class RegeneratePlanRequest(BaseModel):
    user_id: int
    reason: Optional[str] = "manual"


class PlanningChatRequest(BaseModel):
    user_id: int
    message: str


@router.get("/plan/{user_id}")
def get_student_plan(user_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        logger.info("planning_get_plan start user_id=%s refresh=%s", user_id, refresh)
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

        logger.info(
            "planning_get_plan done user_id=%s refresh=%s duration_ms=%s",
            user_id,
            refresh,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return {"ok": True, "plan": plan}
    except HTTPException as exc:
        logger.warning(
            "planning_get_plan rejected user_id=%s refresh=%s status=%s duration_ms=%s detail=%s",
            user_id,
            refresh,
            exc.status_code,
            round((time.perf_counter() - started) * 1000, 2),
            exc.detail,
        )
        return error_json_response(exc.status_code, str(exc.detail), retryable=exc.status_code >= 500)
    except Exception:
        logger.exception(
            "planning_get_plan failed user_id=%s refresh=%s duration_ms=%s",
            user_id,
            refresh,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return error_json_response(
            500,
            "Planning Agent tạm thời chưa thể tải kế hoạch học tập. Vui lòng thử lại sau ít phút.",
            retryable=True,
        )


@router.post("/plan/regenerate")
def regenerate_plan(req: RegeneratePlanRequest, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        logger.info("planning_regenerate start user_id=%s reason=%s", req.user_id, req.reason)
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
        logger.info(
            "planning_regenerate done user_id=%s duration_ms=%s",
            req.user_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return {"ok": True, "message": "Đã tạo lại kế hoạch học tập.", "plan": plan}
    except HTTPException as exc:
        logger.warning(
            "planning_regenerate rejected user_id=%s status=%s duration_ms=%s detail=%s",
            req.user_id,
            exc.status_code,
            round((time.perf_counter() - started) * 1000, 2),
            exc.detail,
        )
        return error_json_response(exc.status_code, str(exc.detail), retryable=exc.status_code >= 500)
    except Exception:
        logger.exception(
            "planning_regenerate failed user_id=%s duration_ms=%s",
            req.user_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return error_json_response(
            500,
            "Planning Agent chưa thể tạo lại kế hoạch lúc này. Vui lòng thử lại sau ít phút.",
            retryable=True,
        )


@router.post("/chat")
def planning_chat(req: PlanningChatRequest, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        logger.info("planning_chat start user_id=%s message=%s", req.user_id, (req.message or "")[:200])
        user = db.query(models.User).filter(models.User.id == req.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

        if user.role != "student":
            raise HTTPException(status_code=403, detail="Chỉ tài khoản sinh viên mới có kế hoạch học tập")

        if not (req.message or "").strip():
            raise HTTPException(status_code=400, detail="Nội dung chat không được để trống")

        agent = PlanningAgent(db)
        result = agent.apply_plan_adjustment(user_id=req.user_id, message=req.message)
        logger.info(
            "planning_chat done user_id=%s duration_ms=%s",
            req.user_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return {
            "ok": True,
            "reply": result.get("message", "Đã cập nhật kế hoạch học tập."),
            "plan": result.get("plan", {}),
        }
    except HTTPException as exc:
        logger.warning(
            "planning_chat rejected user_id=%s status=%s duration_ms=%s detail=%s",
            req.user_id,
            exc.status_code,
            round((time.perf_counter() - started) * 1000, 2),
            exc.detail,
        )
        return error_json_response(exc.status_code, str(exc.detail), retryable=exc.status_code >= 500)
    except Exception:
        logger.exception(
            "planning_chat failed user_id=%s duration_ms=%s",
            req.user_id,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return error_json_response(
            500,
            "Planning Agent chưa thể xử lý yêu cầu thay đổi kế hoạch lúc này. Vui lòng thử lại sau ít phút.",
            retryable=True,
        )


@router.get("/chat/examples")
def planning_chat_examples():
    return {
        "examples": [
            "Đẩy môn Lập trình hướng đối tượng lên học trước",
            "Đưa các tài liệu môn Lưu trữ và phân tích dữ liệu ra học sau",
            "Thêm 2 bài học cho hôm nay",
            "Thêm 2 bài học cho tuần này",
            "Ưu tiên môn cơ sở dữ liệu trong tuần này",
        ]
    }
