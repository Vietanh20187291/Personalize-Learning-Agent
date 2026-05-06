import sys
import logging

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager # Thư viện quản lý vòng đời (lifespan)
from api import assessment, upload, adaptive, stats, auth, classroom, admin, document, exam_generator, subject, teacher_agent, orbit, planning, notification, debug, evaluation
from config import settings
from services.orbit_reminders import start_weekly_orbit_reminder_loop
from logging_config import RequestLoggingMiddleware, error_json_response, get_current_request_id, setup_logging
# --- IMPORT DATABASE VÀ MODELS ---
from db import models
from db.database import engine, SessionLocal 
from db.models import User, Subject

# --- IMPORT HÀM BĂM MẬT KHẨU ---
from api.auth import hash_password 

# --- IMPORT CÁC ROUTER API ---
from api import assessment, upload, adaptive, stats, auth, classroom, admin, document, teacher_agent, orbit, planning, notification, evaluation

from fastapi.staticfiles import StaticFiles
import os
import json
import re
import threading
from datetime import datetime, timedelta
from agents.assessment_agent import AssessmentAgent

setup_logging()
logger = logging.getLogger("app.main")

# Tự động tạo bảng nếu chưa có 
models.Base.metadata.create_all(bind=engine)


def ensure_orbit_login_tracking_column():
    try:
        from sqlalchemy import inspect, text

        inspector = inspect(engine)
        user_columns = [column["name"] for column in inspector.get_columns("users")]
        if "last_login_at" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
                print("✅ Đã bổ sung cột last_login_at cho users")

        columns = [column["name"] for column in inspector.get_columns("student_learning_progress")]
        if "last_login_at" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE student_learning_progress ADD COLUMN last_login_at DATETIME"))
                print("✅ Đã bổ sung cột last_login_at cho student_learning_progress")
        if "previous_login_at" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE student_learning_progress ADD COLUMN previous_login_at DATETIME"))
                print("✅ Đã bổ sung cột previous_login_at cho student_learning_progress")

        tables = inspector.get_table_names()
        if "user_login_sessions" not in tables:
            models.Base.metadata.tables["user_login_sessions"].create(bind=engine, checkfirst=True)
            print("✅ Đã bổ sung bảng user_login_sessions")
        if "student_learning_plan_steps" in tables:
            step_columns = [column["name"] for column in inspector.get_columns("student_learning_plan_steps")]
            if "deadline_date" not in step_columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE student_learning_plan_steps ADD COLUMN deadline_date DATE"))
                    print("✅ Đã bổ sung cột deadline_date cho student_learning_plan_steps")

        # Backfill lịch sử login cho sinh viên cũ chưa có dòng trong user_login_sessions.
        if "user_login_sessions" in tables and "users" in tables:
            db = SessionLocal()
            try:
                student_rows = db.query(models.User).filter(models.User.role == "student").all()
                inserted_sessions = 0
                for student in student_rows:
                    has_session = db.query(models.UserLoginSession.id).filter(
                        models.UserLoginSession.user_id == student.id,
                    ).first() is not None
                    if has_session:
                        continue

                    progress = db.query(models.StudentLearningProgress).filter(
                        models.StudentLearningProgress.user_id == student.id,
                    ).first()

                    login_at = None
                    if progress and progress.last_login_at:
                        login_at = progress.last_login_at
                    elif student.last_login_at:
                        login_at = student.last_login_at

                    if login_at is None:
                        # Không có mốc lịch sử: tạo một phiên cũ để đảm bảo có dữ liệu login in/out.
                        login_at = datetime.utcnow() - timedelta(days=30)

                    logout_at = login_at + timedelta(minutes=30)
                    db.add(models.UserLoginSession(
                        user_id=student.id,
                        login_at=login_at,
                        logout_at=logout_at,
                        duration_seconds=1800,
                    ))
                    inserted_sessions += 1

                if inserted_sessions > 0:
                    db.commit()
                    print(f"✅ Đã backfill {inserted_sessions} dòng user_login_sessions cho sinh viên cũ")
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        # Backfill dữ liệu cũ: mỗi tài liệu đã có điểm sẽ có ít nhất 1 mốc trong bảng lịch sử điểm theo tài liệu.
        if "student_document_score_history" in tables and "student_document_evaluations" in tables:
            db = SessionLocal()
            try:
                existing = {
                    (item.user_id, item.document_id)
                    for item in db.query(models.StudentDocumentScoreHistory).all()
                }
                eval_rows = db.query(models.StudentDocumentEvaluation).filter(
                    models.StudentDocumentEvaluation.attempts > 0,
                ).all()

                inserted = 0
                for item in eval_rows:
                    key = (item.user_id, item.document_id)
                    if key in existing:
                        continue

                    db.add(models.StudentDocumentScoreHistory(
                        user_id=item.user_id,
                        document_id=item.document_id,
                        subject_id=item.subject_id,
                        class_id=item.class_id,
                        score=float(item.latest_score or 0.0),
                        test_type="session",
                        tested_at=item.last_test_at or item.updated_at or item.created_at,
                    ))
                    inserted += 1

                if inserted > 0:
                    db.commit()
                    print(f"✅ Đã backfill {inserted} dòng student_document_score_history từ dữ liệu cũ")
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
    except Exception as e:
        print(f"⚠️ Không thể kiểm tra/cập nhật cột last_login_at: {e}")


ensure_orbit_login_tracking_column()

# --- HÀM TẠO CÁC MÔN HỌC MẶC ĐỊNH ---
def create_default_subjects():
    db = SessionLocal()
    try:
        # Danh sách các môn học phổ thông
        default_subjects = [
            {"name": "Toán học", "icon": "📐"},
            {"name": "Tiếng Anh", "icon": "🌍"},
            {"name": "Lập trình Python", "icon": "🐍"},
            {"name": "Lịch sử", "icon": "📚"},
            {"name": "Địa lý", "icon": "🗺️"},
            {"name": "Vật lý", "icon": "⚛️"},
            {"name": "Hóa học", "icon": "🧪"},
            {"name": "Sinh học", "icon": "🧬"},
            {"name": "Tiếng Việt", "icon": "🇻🇳"},
            {"name": "Tin học", "icon": "💻"},
        ]
        
        for subj_data in default_subjects:
            # Kiểm tra xem môn học đã tồn tại chưa
            existing = db.query(Subject).filter(Subject.name == subj_data["name"]).first()
            if not existing:
                new_subject = Subject(
                    name=subj_data["name"],
                    icon=subj_data.get("icon"),
                    description=f"Môn {subj_data['name']}"
                )
                db.add(new_subject)
                print(f"✅ Tạo môn: {subj_data['name']}")
        
        db.commit()
        print("✅ Hoàn tất khởi tạo danh sách môn học")
    except Exception as e:
        db.rollback()
        print(f"❌ LỖI KHỞI TẠO SUBJECTS: {e}")
    finally:
        db.close()

# --- HÀM TẠO ADMIN MẶC ĐỊNH (SEEDING) ---
def create_initial_admin():
    db = SessionLocal()
    try:
        # Kiểm tra xem tài khoản admin đã tồn tại chưa
        admin_exists = db.query(User).filter(User.username == "admin").first()
        if not admin_exists:
            print("🚀 Đang khởi tạo tài khoản Admin mặc định...")
            admin_user = User(
                username="admin",
                hashed_password=hash_password("admin123"), # Băm mật khẩu mặc định
                role="admin",
                full_name="Quản trị viên hệ thống"
            )
            db.add(admin_user)
            db.commit()
            print("✅ Đã tạo tài khoản Admin mặc định (Tài khoản: admin / Mật khẩu: admin123)")
    except Exception as e:
        # Bắt lỗi rõ ràng để không bị treo server (xoay vòng)
        db.rollback()
        print(f"❌ LỖI KHỞI TẠO ADMIN: {e}")
    finally:
        db.close()


def ensure_document_publications_visible():
    db = SessionLocal()
    try:
        docs = db.query(models.Document).all()
        publications = {
            int(item.doc_id): item
            for item in db.query(models.DocumentPublication).all()
        }

        created = 0
        updated = 0
        for doc in docs:
            publication = publications.get(int(doc.id))
            if publication is None:
                db.add(models.DocumentPublication(doc_id=doc.id, is_visible_to_students=True))
                created += 1
                continue
            if not publication.is_visible_to_students:
                publication.is_visible_to_students = True
                updated += 1

        if created or updated:
            db.commit()
            print(f"✅ Đồng bộ publication tài liệu: created={created}, updated={updated}")
    except Exception as e:
        db.rollback()
        print(f"⚠️ Không thể đồng bộ publication tài liệu: {e}")
    finally:
        db.close()


def warmup_document_question_banks(target_count: int = 20):
    db = SessionLocal()
    try:
        docs = db.query(models.Document).all()
        if not docs:
            print("ℹ️ Không có tài liệu để warmup bộ câu hỏi.")
            return

        agent = AssessmentAgent(db)
        previous_disable_llm = getattr(agent, "_disable_llm_generation", False)
        agent._disable_llm_generation = True
        refreshed = 0
        skipped = 0

        for doc in docs:
            subject_name = (doc.subject or "").strip()
            if not subject_name and getattr(doc, "subject_id", None):
                subject_obj = db.query(models.Subject).filter(models.Subject.id == doc.subject_id).first()
                subject_name = (getattr(subject_obj, "name", "") or "").strip()
            source_file = (doc.filename or "").strip()
            if not subject_name or not source_file:
                skipped += 1
                continue

            rows = db.query(models.QuestionBank).filter(
                models.QuestionBank.subject == subject_name,
                models.QuestionBank.source_file == source_file,
            ).all()

            is_enough = len(rows) >= target_count
            low_diversity = False
            if rows:
                signatures = []
                for row in rows:
                    try:
                        options = json.loads(row.options) if isinstance(row.options, str) else (row.options or [])
                    except Exception:
                        options = []
                    if not isinstance(options, list) or len(options) != 4:
                        continue
                    normalized = []
                    for option in options:
                        text = str(option).strip()
                        text = re.sub(r"^[A-D][\.)]\s*", "", text, flags=re.IGNORECASE)
                        normalized.append(text.lower())
                    signatures.append("|".join(normalized))

                if not signatures:
                    low_diversity = True
                else:
                    unique_count = len(set(signatures))
                    most_common = max(signatures.count(sig) for sig in set(signatures))
                    low_diversity = unique_count <= max(2, len(signatures) // 5) or most_common >= max(4, int(len(signatures) * 0.6))

            if is_enough and not low_diversity:
                skipped += 1
                continue

            generated = agent.pre_generate_questions_for_document(
                subject=subject_name,
                source_file=source_file,
                count=target_count,
                force_refresh=True,
            )
            if generated:
                refreshed += 1

        agent._disable_llm_generation = previous_disable_llm

        print(f"✅ Warmup câu hỏi hoàn tất: regenerated={refreshed}, skipped={skipped}, total_docs={len(docs)}")
    except Exception as exc:
        db.rollback()
        print(f"⚠️ Warmup bộ câu hỏi thất bại: {exc}")
    finally:
        db.close()

# --- QUẢN LÝ VÒNG ĐỜI (LIFESPAN) ---
# Đảm bảo server khởi động xong mới chạy hàm tạo Admin
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_default_subjects()  # Tạo môn học trước
    create_initial_admin()      # Rồi tạo admin
    ensure_document_publications_visible()
    warmup_enabled = os.getenv("ENABLE_QUESTION_BANK_WARMUP", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if warmup_enabled:
        threading.Thread(
            target=warmup_document_question_banks,
            kwargs={"target_count": 20},
            daemon=True,
            name="question-bank-warmup",
        ).start()
        logger.info("Question bank warmup thread started.")
    else:
        logger.info("Question bank warmup disabled. Set ENABLE_QUESTION_BANK_WARMUP=true to enable it.")
    logger.info(
        "RAG embeddings enabled=%s",
        getattr(settings, "RAG_EMBEDDINGS_ENABLED", True),
    )
    start_weekly_orbit_reminder_loop(SessionLocal)
    yield

# Khởi tạo App với lifespan
app = FastAPI(title="AI Personalized Learning API", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Yêu cầu không hợp lệ hoặc không thể xử lý."
    logger.warning(
        "http_exception method=%s path=%s status=%s request_id=%s detail=%s",
        request.method,
        request.url.path,
        exc.status_code,
        get_current_request_id(),
        detail,
    )
    return error_json_response(exc.status_code, detail, retryable=exc.status_code >= 500)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_exception method=%s path=%s request_id=%s",
        request.method,
        request.url.path,
        get_current_request_id(),
    )
    return error_json_response(
        500,
        "Máy chủ tạm thời chưa thể hoàn tất yêu cầu này. Vui lòng thử lại sau ít phút.",
        retryable=True,
    )

# --- CẤU HÌNH CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("temp_uploads", exist_ok=True) # Đảm bảo thư mục tồn tại để không báo lỗi
app.mount("/temp_uploads", StaticFiles(directory="temp_uploads"), name="temp_uploads")

# --- ĐĂNG KÝ ROUTER ---

# 0. Authentication (Xử lý Đăng nhập/Đăng ký)
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])

# 1. Classroom (Xử lý Tạo lớp, Tham gia lớp, Lấy danh sách lớp)
app.include_router(classroom.router, prefix="/api/classroom", tags=["Classroom"])

# 2. Assessment
app.include_router(assessment.router, prefix="/api/assessment", tags=["Assessment"])

# 3. Upload (Quản lý tài liệu theo lớp)
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])

# 4. Adaptive (Gia sư AI cá nhân hóa theo tài liệu lớp)
app.include_router(adaptive.router, prefix="/api/adaptive", tags=["AI Tutor"])

# 5. Stats
app.include_router(stats.router, prefix="/api/stats", tags=["Statistics"])

# 6. Admin (Quản lý người dùng - Giáo viên/Học sinh)
app.include_router(evaluation.router, prefix="/api/evaluation", tags=["Evaluation AI"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])

# 7. Document (Quản lý Thư viện học liệu) 
app.include_router(document.router, prefix="/api/documents", tags=["Document"])

# 8. Subject (Quản lý môn học độc lập)
app.include_router(subject.router, prefix="/api/subjects", tags=["Subject"])

# 8. Exam Generator (Sinh đề thi file Word)
app.include_router(exam_generator.router, prefix="/api/exam", tags=["Exam"])

# 9. Teacher Agent (Hỗ trợ giảng viên)
app.include_router(teacher_agent.router, prefix="/api/teacher", tags=["Teacher AI"])

# 10. Orbit Agent (Hỗ trợ sinh viên)
app.include_router(orbit.router, prefix="/api/orbit", tags=["Orbit AI"])

# 11. Planning Agent (Kế hoạch học tập theo tài liệu)
app.include_router(planning.router, prefix="/api/planning", tags=["Planning AI"])

# 12. Notifications
app.include_router(notification.router, prefix="/api/notifications", tags=["Notifications"])

# 13. Debug (Real-time LLM debugging via SSE)
app.include_router(debug.router, tags=["Debug"])
app.include_router(debug.router, prefix="/api", tags=["Debug"])

@app.get("/")
def read_root():
    return {"message": "Hệ thống AI Learning đã sẵn sàng!"}


@app.get("/api/health")
def health_check():
    return {
        "ok": True,
        "message": "Backend đang hoạt động",
        "rag_embeddings_enabled": getattr(settings, "RAG_EMBEDDINGS_ENABLED", True),
    }
