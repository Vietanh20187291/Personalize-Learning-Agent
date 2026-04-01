import shutil
import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional, List
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db.database import get_db
from db import models
from agents.content_agent import content_agent 
from rag.vector_store import get_vector_store

router = APIRouter()


class DocumentUpdateRequest(BaseModel):
    title: str


class DocumentVisibilityRequest(BaseModel):
    is_visible_to_students: bool

# --- HÀM PHỤ TRỢ ---
def validate_file_extension(filename: str):
    # Keep this list in sync with ContentAgent._get_loader support.
    allowed_extensions = {".pdf", ".docx", ".pptx", ".txt"}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File không hỗ trợ. Chỉ nhận: {', '.join(allowed_extensions)}")

# --- API 1: PHÂN TÍCH MÔN HỌC ---
@router.post("/analyze-subject")
async def analyze_document_subject(file: UploadFile = File(...)):
    validate_file_extension(file.filename) 
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    safe_filename = file.filename.replace(" ", "_")
    file_path = os.path.join(temp_dir, safe_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        suggested_subject = content_agent.quick_analyze(file_path)
        return {"suggested_subject": suggested_subject, "filename": safe_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# --- API 2: UPLOAD VÀ LƯU DATABASE ---
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    manual_subject: Optional[str] = Form(None),
    teacher_id: Optional[int] = Form(None),
    class_id: Optional[int] = Form(None), 
    db: Session = Depends(get_db)
):
    validate_file_extension(file.filename)
    
    if not class_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn một lớp học để nạp tài liệu.")

    # Lấy lớp học để get subject_id
    classroom = db.query(models.Classroom).filter(models.Classroom.id == class_id).first()
    if not classroom:
        raise HTTPException(status_code=400, detail="Lớp học không tồn tại.")
    
    subject_id = classroom.subject_id
    subject_name = classroom.subject

    safe_filename = file.filename.replace(" ", "_")
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, safe_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Xử lý RAG thông qua Content Agent
        # Ưu tiên môn học của lớp đã chọn để tránh lệch môn khi AI auto-detect.
        effective_subject = (manual_subject or "").strip()
        if not effective_subject or effective_subject == "Tự động nhận diện":
            effective_subject = subject_name or "Khác"

        result = content_agent.process_file(file_path, manual_subject=effective_subject)
        
        if result and result.get("success"):
            final_subject = result.get("subject", subject_name or "Khác")
            
            # Lưu thông tin tài liệu vào SQL với subject_id mới
            new_doc = models.Document(
                title=safe_filename,
                filename=safe_filename, 
                subject_id=subject_id,  # MỚI: Dùng subject_id
                subject=final_subject,  # DEPRECATED: Giữ để backward compat
                teacher_id=teacher_id,
                class_id=class_id # <--- GẮN TÀI LIỆU VÀO LỚP CỤ THỂ
            )
            db.add(new_doc)
            db.flush()

            # Mặc định KHÔNG hiển thị cho sinh viên đến khi giáo viên bật.
            publication = models.DocumentPublication(
                doc_id=new_doc.id,
                is_visible_to_students=False,
            )
            db.add(publication)
            db.commit()
            db.refresh(new_doc)

            return {
                "id": new_doc.id,
                "filename": safe_filename, 
                "subject_id": subject_id,
                "subject": final_subject,
                "class_id": class_id,
                "message": f"✅ Tài liệu đã được nạp riêng cho lớp học này."
            }
        else:
            raise HTTPException(status_code=500, detail="Lỗi xử lý nội dung RAG")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # if os.path.exists(file_path):
        #     os.remove(file_path)
        pass

# --- API 3: LẤY DANH SÁCH FILE CỦA GIÁO VIÊN/LỚP ---
@router.get("/documents")
async def get_documents(teacher_id: Optional[int] = None, class_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(models.Document)
    
    if class_id:
        query = query.filter(models.Document.class_id == class_id)
    elif teacher_id:
        query = query.filter(models.Document.teacher_id == teacher_id)
        
    docs = query.order_by(models.Document.upload_time.desc()).all()
    doc_ids = [doc.id for doc in docs]
    visibility_map = {}
    if doc_ids:
        rows = db.query(models.DocumentPublication).filter(models.DocumentPublication.doc_id.in_(doc_ids)).all()
        visibility_map = {row.doc_id: row.is_visible_to_students for row in rows}

    return [
        {
            "id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "subject": doc.subject,
            "subject_id": doc.subject_id,
            "upload_time": doc.upload_time,
            "teacher_id": doc.teacher_id,
            "class_id": doc.class_id,
            "is_visible_to_students": visibility_map.get(doc.id, False),
        }
        for doc in docs
    ]


@router.put("/documents/{doc_id}")
async def update_document_metadata(doc_id: int, payload: DocumentUpdateRequest, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    clean_title = payload.title.strip()
    if not clean_title:
        raise HTTPException(status_code=400, detail="Tiêu đề tài liệu không được để trống.")

    doc.title = clean_title
    db.commit()
    db.refresh(doc)
    return {
        "message": "Cập nhật tài liệu thành công",
        "id": doc.id,
        "title": doc.title,
    }


@router.put("/documents/{doc_id}/visibility")
async def update_document_visibility(doc_id: int, payload: DocumentVisibilityRequest, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    publication = db.query(models.DocumentPublication).filter(models.DocumentPublication.doc_id == doc_id).first()
    if not publication:
        publication = models.DocumentPublication(doc_id=doc_id)
        db.add(publication)

    publication.is_visible_to_students = payload.is_visible_to_students
    db.commit()

    return {
        "message": "Cập nhật quyền hiển thị tài liệu thành công",
        "id": doc_id,
        "is_visible_to_students": publication.is_visible_to_students,
    }

# --- API 4: XÓA TÀI LIỆU TRIỆT ĐỂ ---
@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    try:
        filename = doc.filename
        vector_store = get_vector_store()
        
        # Quét và xóa trong Vector DB
        all_data = vector_store.get()
        ids = all_data.get("ids", [])
        metadatas = all_data.get("metadatas", [])
        
        ids_to_delete = []
        for i, meta in enumerate(metadatas):
            if any(filename in str(val) for val in meta.values()):
                ids_to_delete.append(ids[i])

        if ids_to_delete:
            vector_store.delete(ids=ids_to_delete)

        # Xóa trong SQL (Chunks và Document)
        db.query(models.Chunk).filter(models.Chunk.source_file == filename).delete()
        db.delete(doc)
        
        db.commit()
        return {"message": f"✅ Đã dọn dẹp sạch sẽ tri thức của: {filename}"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa: {str(e)}")