from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db.database import get_db
from db.models import (
    Subject,
    User,
    Classroom,
    Document,
    LearningRoadmap,
    LearnerProfile,
    StudySession,
    AssessmentHistory,
    QuestionBank,
    Chunk,
    AssessmentResult,
)
from api.auth import get_current_user

router = APIRouter()


class SubjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None


class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None


def get_current_teacher(current_user: User = Depends(get_current_user)):
    if current_user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ tài khoản Giáo viên mới có quyền quản lý môn học."
        )
    return current_user


@router.get("")
def list_subjects(db: Session = Depends(get_db)):
    subjects = db.query(Subject).order_by(Subject.name.asc()).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "icon": s.icon,
            "class_count": len(s.classrooms),
        }
        for s in subjects
    ]


@router.get("/{subject_id}")
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Không tìm thấy môn học")

    return {
        "id": subject.id,
        "name": subject.name,
        "description": subject.description,
        "icon": subject.icon,
        "class_count": len(subject.classrooms),
    }


@router.post("")
def create_subject(data: SubjectCreate, db: Session = Depends(get_db), _: User = Depends(get_current_teacher)):
    clean_name = data.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Tên môn học không được để trống")

    existing = db.query(Subject).filter(Subject.name.ilike(clean_name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Môn học đã tồn tại")

    new_subject = Subject(
        name=clean_name,
        description=data.description.strip() if data.description else None,
        icon=data.icon.strip() if data.icon else None,
    )
    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)

    return {
        "message": "Tạo môn học thành công",
        "id": new_subject.id,
        "name": new_subject.name,
        "description": new_subject.description,
        "icon": new_subject.icon,
    }


@router.put("/{subject_id}")
def update_subject(subject_id: int, data: SubjectUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_teacher)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Không tìm thấy môn học")

    if data.name is not None:
        clean_name = data.name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Tên môn học không được để trống")

        duplicate = db.query(Subject).filter(Subject.name.ilike(clean_name), Subject.id != subject_id).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Tên môn học đã tồn tại")

        subject.name = clean_name

        # Đồng bộ tên môn ở cột subject deprecated để không vỡ luồng cũ
        db.query(Classroom).filter(Classroom.subject_id == subject_id).update({Classroom.subject: clean_name})
        db.query(Document).filter(Document.subject_id == subject_id).update({Document.subject: clean_name})
        db.query(LearningRoadmap).filter(LearningRoadmap.subject_id == subject_id).update({LearningRoadmap.subject: clean_name})
        db.query(LearnerProfile).filter(LearnerProfile.subject_id == subject_id).update({LearnerProfile.subject: clean_name})
        db.query(StudySession).filter(StudySession.subject_id == subject_id).update({StudySession.subject: clean_name})
        db.query(AssessmentHistory).filter(AssessmentHistory.subject_id == subject_id).update({AssessmentHistory.subject: clean_name})
        db.query(QuestionBank).filter(QuestionBank.subject_id == subject_id).update({QuestionBank.subject: clean_name})
        db.query(Chunk).filter(Chunk.subject_id == subject_id).update({Chunk.subject: clean_name})
        db.query(AssessmentResult).filter(AssessmentResult.subject_id == subject_id).update({AssessmentResult.subject: clean_name})

    if data.description is not None:
        subject.description = data.description.strip() if data.description else None

    if data.icon is not None:
        subject.icon = data.icon.strip() if data.icon else None

    db.commit()
    db.refresh(subject)

    return {
        "message": "Cập nhật môn học thành công",
        "id": subject.id,
        "name": subject.name,
        "description": subject.description,
        "icon": subject.icon,
    }


@router.delete("/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_teacher)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Không tìm thấy môn học")

    in_use = db.query(Classroom).filter(Classroom.subject_id == subject_id).first()
    if in_use:
        raise HTTPException(
            status_code=400,
            detail="Không thể xóa môn học đang có lớp học. Vui lòng xóa/chuyển lớp trước."
        )

    db.delete(subject)
    db.commit()
    return {"message": "Xóa môn học thành công"}
