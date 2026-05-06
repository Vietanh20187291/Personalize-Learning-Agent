from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import models
from db.database import get_db

router = APIRouter()


class NotificationCreateRequest(BaseModel):
    recipient_user_id: int
    actor_user_id: int | None = None
    type: str = "general"
    title: str
    body: str = ""
    metadata_json: dict | None = None


class NotificationReadRequest(BaseModel):
    notification_id: int


@router.get("/{user_id}")
def list_notifications(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    rows = db.query(models.Notification).filter(
        models.Notification.recipient_user_id == user_id,
    ).order_by(models.Notification.created_at.desc(), models.Notification.id.desc()).limit(50).all()

    unread_count = db.query(models.Notification).filter(
        models.Notification.recipient_user_id == user_id,
        models.Notification.is_read == False,
    ).count()

    return {
        "unread_count": int(unread_count),
        "items": [
            {
                "id": row.id,
                "type": row.type,
                "title": row.title,
                "body": row.body,
                "metadata": row.metadata_json or {},
                "is_read": bool(row.is_read),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.post("/create")
def create_notification(req: NotificationCreateRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == req.recipient_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người nhận thông báo")

    row = models.Notification(
        recipient_user_id=req.recipient_user_id,
        actor_user_id=req.actor_user_id,
        type=(req.type or "general").strip() or "general",
        title=(req.title or "").strip(),
        body=(req.body or "").strip(),
        metadata_json=req.metadata_json or {},
        is_read=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "message": "Đã tạo notification"}


@router.post("/mark-read")
def mark_notification_read(req: NotificationReadRequest, db: Session = Depends(get_db)):
    row = db.query(models.Notification).filter(models.Notification.id == req.notification_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy notification")
    row.is_read = True
    db.commit()
    return {"ok": True, "id": row.id}


@router.post("/mark-all-read/{user_id}")
def mark_all_notifications_read(user_id: int, db: Session = Depends(get_db)):
    db.query(models.Notification).filter(
        models.Notification.recipient_user_id == user_id,
        models.Notification.is_read == False,
    ).update({models.Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
