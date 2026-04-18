import os
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse 
from sqlalchemy.orm import Session
from db.database import get_db
from db import models
from typing import Optional
from datetime import timedelta
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from pptx import Presentation

# Import hàm lấy vector store
from rag.vector_store import get_vector_store 

router = APIRouter()


def _resolve_document_file_path(filename: str) -> Path:
    """Resolve uploaded file path independent of current working directory."""
    safe_name = (filename or "").strip()
    if not safe_name:
        raise HTTPException(status_code=404, detail="Tên file tài liệu không hợp lệ")

    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        project_root / "temp_uploads" / safe_name,
        project_root / "backend" / "temp_uploads" / safe_name,
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    raise HTTPException(status_code=404, detail="File vật lý không tồn tại trên server")


def _can_student_access_document(db: Session, doc: models.Document, user_id: Optional[int]) -> bool:
    publication = db.query(models.DocumentPublication).filter(models.DocumentPublication.doc_id == doc.id).first()
    if publication and publication.is_visible_to_students:
        return True

    if not user_id:
        return False

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or getattr(user, "role", None) != "student":
        return False

    enrolled_class_ids = {classroom.id for classroom in (getattr(user, "enrolled_classes", []) or [])}
    return bool(doc.class_id and doc.class_id in enrolled_class_ids)


def _extract_preview_segments(file_path: str, filename: str):
    """Trích xuất nội dung text từ các file để hiển thị preview.
    Format tốt hơn để presentation rõ ràng.
    """
    ext = os.path.splitext(filename)[1].lower()
    
    try:
        if ext == ".pptx":
            slides = []
            try:
                prs = Presentation(file_path)
                for i, slide in enumerate(prs.slides, start=1):
                    slide_lines = []
                    
                    for shape in slide.shapes:
                        try:
                            if hasattr(shape, "text_frame"):
                                for paragraph in shape.text_frame.paragraphs:
                                    text = " ".join(paragraph.text.split()).strip()
                                    if text:
                                        slide_lines.append(text)
                            elif hasattr(shape, "text") and isinstance(shape.text, str):
                                text = " ".join(shape.text.split()).strip()
                                if text:
                                    slide_lines.append(text)
                        except Exception as shape_err:
                            continue
                    
                    if slide_lines:
                        # Format better: join with bullet points
                        formatted_content = "\n".join([f"• {line}" for line in slide_lines])
                        slides.append({
                            "title": f"📊 Slide {i}",
                            "content": formatted_content
                        })
                
                if slides:
                    return {"type": "pptx", "segments": slides}
                else:
                    return {"type": "pptx", "segments": []}
                    
            except Exception as pptx_err:
                print(f"❌ Lỗi parse PPTX '{filename}': {pptx_err}")
                return {"type": "pptx", "segments": []}

        if ext == ".pdf":
            pages = []
            try:
                loader = PyPDFLoader(file_path)
                docs = loader.load()
                
                for idx, doc in enumerate(docs, start=1):
                    text = " ".join((doc.page_content or "").split()).strip()
                    if text:
                        pages.append({
                            "title": f"📄 Trang {idx}",
                            "content": text[:500] + ("..." if len(text) > 500 else "")
                        })
                
                if pages:
                    return {"type": "pdf", "segments": pages}
                else:
                    return {"type": "pdf", "segments": []}
                    
            except Exception as pdf_err:
                print(f"❌ Lỗi parse PDF '{filename}': {pdf_err}")
                return {"type": "pdf", "segments": []}

        if ext == ".docx":
            try:
                loader = Docx2txtLoader(file_path)
                docs = loader.load()
                content = "\n".join([(d.page_content or "").strip() for d in docs if (d.page_content or "").strip()])
                
                blocks = [b.strip() for b in content.split("\n") if b.strip()]
                
                if blocks:
                    segments = [{"title": f"📋 Đoạn {i+1}", "content": b} for i, b in enumerate(blocks[:150])]
                    return {"type": "docx", "segments": segments}
                else:
                    return {"type": "docx", "segments": []}
                    
            except Exception as docx_err:
                print(f"❌ Lỗi parse DOCX '{filename}': {docx_err}")
                return {"type": "docx", "segments": []}

        if ext == ".txt":
            try:
                loader = TextLoader(file_path, encoding="utf-8")
                docs = loader.load()
                content = "\n".join([(d.page_content or "").strip() for d in docs if (d.page_content or "").strip()])
                
                blocks = [b.strip() for b in content.split("\n") if b.strip()]
                
                if blocks:
                    segments = [{"title": f"📝 Dòng {i+1}", "content": b} for i, b in enumerate(blocks[:200])]
                    return {"type": "txt", "segments": segments}
                else:
                    return {"type": "txt", "segments": []}
                    
            except Exception as txt_err:
                print(f"⚠️ Lỗi parse TXT (UTF-8) '{filename}': {txt_err}")
                try:
                    loader = TextLoader(file_path, encoding="cp1252")
                    docs = loader.load()
                    content = "\n".join([(d.page_content or "").strip() for d in docs if (d.page_content or "").strip()])
                    blocks = [b.strip() for b in content.split("\n") if b.strip()]
                    
                    if blocks:
                        segments = [{"title": f"📝 Dòng {i+1}", "content": b} for i, b in enumerate(blocks[:200])]
                        return {"type": "txt", "segments": segments}
                except:
                    pass
                return {"type": "txt", "segments": []}

        return {"type": "unknown", "segments": []}
        
    except Exception as general_err:
        print(f"❌ Lỗi chung khi parse '{filename}': {general_err}")
        return {"type": "unknown", "segments": []}


def _extract_preview_from_vector(source_filename: str):
    try:
        vector_store = get_vector_store()
        collection = vector_store._collection
        data = collection.get(include=["documents", "metadatas"])
        docs = data.get("documents", []) or []
        metas = data.get("metadatas", []) or []

        matched = []
        for i, meta in enumerate(metas):
            source = ""
            if meta and isinstance(meta, dict):
                source = str(meta.get("source", ""))
            if os.path.basename(source) == source_filename:
                txt = str(docs[i] or "").strip()
                if txt:
                    matched.append(txt)

        segments = [
            {"title": f"Nội dung {idx + 1}", "content": text}
            for idx, text in enumerate(matched[:80])
        ]
        return segments
    except Exception:
        return []

# ==========================================
# 1. API CHO GIÁO VIÊN: LẤY DANH SÁCH TÀI LIỆU
# ==========================================
@router.get("/class-documents/{class_id}")
def get_documents(
    class_id: int, 
    subject: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """Lấy danh sách tài liệu của một lớp với múi giờ VN"""
    query = db.query(models.Document).filter(models.Document.class_id == class_id)
    
    if subject and subject != "all":
        query = query.filter(models.Document.subject == subject)
        
    docs = query.order_by(models.Document.upload_time.desc()).all()
    
    results = []
    for doc in docs:
        # FIX GIỜ VIỆT NAM (UTC+7)
        time_str = (doc.upload_time + timedelta(hours=7)).strftime("%H:%M - %d/%m/%Y") if doc.upload_time else "Chưa xác định"
        
        results.append({
            "id": doc.id,
            "title": doc.filename, 
            "subject": doc.subject,
            "file_path": f"temp_uploads/{doc.filename}", 
            "created_at": time_str 
        })
        
    return results

# ==========================================
# 2. API CHO GIÁO VIÊN: XÓA TÀI LIỆU
# ==========================================
@router.delete("/delete/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """Xóa tài liệu hoàn toàn khỏi 3 nơi: File vật lý, ChromaDB và SQLite"""
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    
    filename = doc.filename

    # --- 1. XÓA FILE VẬT LÝ TRONG THƯ MỤC TEMP_UPLOADS ---
    if filename:
        file_path = os.path.join("temp_uploads", filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"✅ Đã dọn dẹp file vật lý: {file_path}")
            except Exception as e:
                print(f"❌ Lỗi khi xóa file vật lý: {e}")

    # --- 2. XÓA TRI THỨC TRONG CHROMADB ---
    try:
        vector_store = get_vector_store()
        
        # Lấy trực tiếp đối tượng Collection gốc của ChromaDB thay vì dùng vỏ bọc LangChain
        collection = vector_store._collection
        
        # Ép Collection phải trả về TOÀN BỘ dữ liệu metadatas (không bị limit)
        all_data = collection.get(include=["metadatas"])
        ids = all_data.get("ids", [])
        metadatas = all_data.get("metadatas", [])
        
        ids_to_delete = []
        for i, meta in enumerate(metadatas):
            if meta and "source" in meta:
                source_path = str(meta["source"])
                # Miễn là tên file có xuất hiện trong đường dẫn thì gom vào danh sách tử hình
                if filename in source_path:
                    ids_to_delete.append(ids[i])

        if ids_to_delete:
            # Lệnh xóa ép buộc từ Core ChromaDB
            collection.delete(ids=ids_to_delete)
            print(f"✅ Đã dọn dẹp sạch {len(ids_to_delete)} đoạn băm của {filename} trong ChromaDB")
        else:
            print(f"⚠️ Không tìm thấy tri thức của {filename} trong ChromaDB")
            
    except Exception as e:
        print(f"⚠️ Lỗi khi dọn dẹp ChromaDB: {e}")

    # --- 3. XÓA DỮ LIỆU TRONG SQLITE ---
    try:
        # Xóa các Chunks liên quan trong bảng chunks (nếu có)
        db.query(models.Chunk).filter(models.Chunk.source_file == filename).delete()
        
        # Xóa bản ghi trong bảng documents
        db.delete(doc)
        db.commit()
        return {"message": "Đã xóa tài liệu và tri thức AI thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi database: {str(e)}")

# ==========================================
# 3. API CHO HỌC SINH: LẤY DANH SÁCH TÀI LIỆU
# ==========================================
@router.get("/student/{user_id}")
def get_student_documents(user_id: int, subject: Optional[str] = None, db: Session = Depends(get_db)):
    """Lấy danh sách tài liệu dành cho học sinh dựa vào các lớp đã tham gia"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh")

    # Lấy danh sách ID các lớp mà học sinh đang tham gia
    enrolled_class_ids = [c.id for c in getattr(user, 'enrolled_classes', [])]
    
    if not enrolled_class_ids:
        return []

    # Chỉ lấy tài liệu thuộc các lớp đã tham gia VÀ được giáo viên bật hiển thị.
    query = db.query(models.Document, models.DocumentPublication).join(
        models.DocumentPublication,
        models.DocumentPublication.doc_id == models.Document.id,
    ).filter(
        models.Document.class_id.in_(enrolled_class_ids),
        models.DocumentPublication.is_visible_to_students == True,
    )
    
    # Nếu có chọn môn cụ thể thì lọc thêm theo môn
    if subject and subject != "Tất cả":
        query = query.filter(models.Document.subject == subject)
        
    docs = query.order_by(models.Document.id.desc()).all()
    
    result = []
    for doc, publication in docs:
        time_str = (doc.upload_time + timedelta(hours=7)).strftime("%H:%M - %d/%m/%Y") if doc.upload_time else "Chưa xác định"
        result.append({
            "id": doc.id,
            "filename": doc.filename,
            "subject": doc.subject,
            "class_id": doc.class_id,
            "upload_time": time_str,
            "is_visible_to_students": publication.is_visible_to_students,
        })
        
    return result

# ==========================================
# 4. API CHUNG: TẢI FILE VỀ MÁY (DOWNLOAD)
# ==========================================
@router.get("/download/{doc_id}")
def download_document(doc_id: int, db: Session = Depends(get_db)):
    """API cho phép tải file vật lý về thiết bị"""
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại")

    publication = db.query(models.DocumentPublication).filter(models.DocumentPublication.doc_id == doc_id).first()
    if not publication or not publication.is_visible_to_students:
        raise HTTPException(status_code=403, detail="Tài liệu này chưa được giáo viên cho phép hiển thị")
        
    # Trỏ đúng vào thư mục temp_uploads theo logic lưu file
    file_path = _resolve_document_file_path(doc.filename)
        
    return FileResponse(
        path=str(file_path), 
        filename=doc.filename,
        media_type='application/octet-stream' # Ép trình duyệt tự động tải file xuống
    )


@router.get("/view/{doc_id}")
def view_document_inline(doc_id: int, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """API hiển thị file trực tiếp (inline) để nhúng preview PDF/PPT trong frontend."""
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại")

    if not _can_student_access_document(db, doc, user_id):
        raise HTTPException(status_code=403, detail="Tài liệu này chưa được giáo viên cho phép hiển thị")

    file_path = _resolve_document_file_path(doc.filename)

    ext = os.path.splitext(doc.filename)[1].lower()
    media_map = {
        ".pdf": "application/pdf",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    media_type = media_map.get(ext, "application/octet-stream")

    safe_filename = re.sub(r'[^A-Za-z0-9._-]+', '_', doc.filename or 'document')

    def iter_file_bytes(path: Path, chunk_size: int = 1024 * 1024):
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        iter_file_bytes(file_path),
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename=\"{safe_filename}\"",
            "Accept-Ranges": "bytes",
            "X-Doc-View-Version": "v4_stream_unicode_fix",
        },
    )


@router.get("/preview/{doc_id}")
def preview_document(doc_id: int, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Trích xuất nội dung text để preview trực tiếp trong ứng dụng."""
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Tài liệu không tồn tại")

    if not _can_student_access_document(db, doc, user_id):
        raise HTTPException(status_code=403, detail="Tài liệu này chưa được giáo viên cho phép hiển thị")

    file_path = _resolve_document_file_path(doc.filename)

    try:
        parsed = _extract_preview_segments(str(file_path), doc.filename)
        segments = parsed.get("segments", [])
        if not segments:
            segments = _extract_preview_from_vector(doc.filename)
        return {
            "doc_id": doc.id,
            "filename": doc.filename,
            "file_type": parsed.get("type", "unknown"),
            "segments": segments,
        }
    except Exception as e:
        fallback_segments = _extract_preview_from_vector(doc.filename)
        if fallback_segments:
            return {
                "doc_id": doc.id,
                "filename": doc.filename,
                "file_type": "vector_fallback",
                "segments": fallback_segments,
            }
        raise HTTPException(status_code=500, detail=f"Không thể preview tài liệu: {str(e)}")