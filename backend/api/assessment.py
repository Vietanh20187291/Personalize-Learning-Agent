from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.database import SessionLocal, get_db, engine, Base
from db.models import LearnerProfile, QuestionBank, AssessmentHistory, StudentLearningProgress, StudentDocumentEvaluation, StudentDocumentScoreHistory, User, Document, LearningRoadmap, Classroom, Subject, UserLoginSession, WrongAnswerRecord
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import json
import re
import logging
from sqlalchemy import func

from agents.assessment_agent import AssessmentAgent
from agents.evaluation_agent import EvaluationAgent
from agents.profiling_agent import ProfilingAgent
from agents.adaptive_agent import AdaptiveAgent 
from services.score_metrics import compute_subject_score_metrics

router = APIRouter()
logger = logging.getLogger("app.assessment")


def _sanitize_question_bank_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = re.sub(r"\s+#\d+\b", "", cleaned)
    cleaned = re.sub(r"\s*\(\s*mức\s*cơ\s*bản\s*,\s*câu\s*\d+\s*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\s*(?:Trọng tâm|Trong ngữ cảnh|Khi xét|Trong phạm vi)\s*:\s*[^.?!;]+[.?!;:]*\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_question_bank_options(raw_options) -> List[str]:
    try:
        parsed = json.loads(raw_options) if isinstance(raw_options, str) else raw_options
    except Exception:
        parsed = []

    if not isinstance(parsed, list):
        return []

    normalized = []
    for option in parsed:
        text = _sanitize_question_bank_text(str(option))
        if text:
            normalized.append(text)
    return normalized

# --- HELPER FUNCTION: CONVERT SUBJECT STRING TO SUBJECT_ID ---
def get_subject_id(subject_name: str, db: Session) -> int:
    """Convert subject name (string) to subject_id. Auto-create if not found."""
    if not subject_name:
        raise HTTPException(status_code=400, detail="Subject không được rỗng")
    
    subject = db.query(Subject).filter(Subject.name.ilike(subject_name.strip())).first()
    if subject:
        return subject.id
    
    # Auto-create subject if not found (backward compat)
    new_subject = Subject(name=subject_name.strip(), description=f"Môn {subject_name.strip()}")
    db.add(new_subject)
    db.flush()
    return new_subject.id

def _compute_effort_score(db: Session, user_id: int) -> float:
    login_seconds = sum(
        int(item.duration_seconds or 0)
        for item in db.query(UserLoginSession).filter(UserLoginSession.user_id == user_id).all()
    )
    total_minutes = int(login_seconds // 60)
    expected_login_minutes = 600
    if expected_login_minutes <= 0:
        return 0.0
    return round(min((total_minutes / expected_login_minutes) * 100, 100), 2)


def _build_fast_feedback(score_percent: float, passed: bool, is_session_quiz: bool) -> str:
    if is_session_quiz:
        if passed:
            return "Bạn đã hoàn thành bài kiểm tra. Hệ thống đang cập nhật đánh giá chi tiết."
        return "Bạn đã nộp bài. Hệ thống đang tổng hợp phần cần ôn lại cho bạn."
    if score_percent >= 80:
        return "Kết quả rất tốt. Hệ thống đang cập nhật đánh giá chi tiết của bạn."
    if score_percent >= 60:
        return "Bạn đã đạt yêu cầu. Hệ thống đang cập nhật thêm đánh giá học tập."
    return "Bạn đã nộp bài. Hệ thống đang cập nhật gợi ý ôn tập cho phần còn yếu."


def _run_post_submit_updates(
    req_payload: dict,
    subject_id: int,
    old_level: str,
    final_test_type: str,
    score_percent: float,
    correct_count: int,
    total_q: int,
):
    db = SessionLocal()
    try:
        req_user_id = int(req_payload.get("user_id"))
        req_subject = str(req_payload.get("subject") or "")
        req_is_session_quiz = bool(req_payload.get("is_session_quiz"))
        req_session_number = req_payload.get("session_number")
        req_session_topic = req_payload.get("session_topic")
        req_source_file = req_payload.get("source_file")
        req_force_level = req_payload.get("force_level")

        profile = db.query(LearnerProfile).filter_by(subject_id=subject_id, user_id=req_user_id).first()
        if not profile:
            profile = db.query(LearnerProfile).filter_by(subject=req_subject, user_id=req_user_id).first()

        profiler = ProfilingAgent(db)
        calculated_level = profiler.classify_learner(correct_count, total_q, req_subject, req_user_id)
        new_level = old_level if req_is_session_quiz else calculated_level

        roadmap = db.query(LearningRoadmap).filter_by(user_id=req_user_id, subject_id=subject_id).first()
        if not roadmap:
            roadmap = db.query(LearningRoadmap).filter_by(user_id=req_user_id, subject=req_subject).first()

        user_obj = db.query(User).filter(User.id == req_user_id).first()
        target_class = next((c for c in getattr(user_obj, 'enrolled_classes', []) if c.subject == req_subject), None)
        allowed_filenames = []
        if target_class:
            allowed_docs = db.query(Document).filter(
                Document.class_id == target_class.id,
                Document.subject_id == target_class.subject_id
            ).all()
            allowed_filenames = [doc.filename for doc in allowed_docs]

        adaptive_agent = None
        if not roadmap:
            try:
                adaptive_agent = AdaptiveAgent(db)
                adaptive_agent.generate_overall_roadmap(req_user_id, req_subject, allowed_filenames, force_level=req_force_level or new_level)
            except Exception as e:
                print(f"🚨 CẢNH BÁO AI CRASH ROADMAP: {e}")
        else:
            total_sessions = len(roadmap.roadmap_data) if roadmap.roadmap_data else 11
            if req_is_session_quiz:
                required_correct = 4
                passed = correct_count >= required_correct
                if passed:
                    if req_session_number and req_session_number != roadmap.current_session:
                        pass
                    elif roadmap.current_session < total_sessions:
                        roadmap.current_session += 1
                    else:
                        roadmap.is_completed = True
            elif score_percent >= 60.0:
                if roadmap.current_session < total_sessions:
                    roadmap.current_session += 1
                else:
                    current_lvl = roadmap.level_assigned
                    if current_lvl == "Beginner":
                        roadmap.level_assigned = "Intermediate"
                        roadmap.current_session = 1
                        new_level = "Intermediate"
                        if profile:
                            profile.current_level = "Intermediate"
                        try:
                            adaptive_agent = adaptive_agent or AdaptiveAgent(db)
                            adaptive_agent.generate_overall_roadmap(req_user_id, req_subject, allowed_filenames, force_level="Intermediate")
                        except Exception:
                            pass
                    elif current_lvl == "Intermediate":
                        roadmap.level_assigned = "Advanced"
                        roadmap.current_session = 1
                        new_level = "Advanced"
                        if profile:
                            profile.current_level = "Advanced"
                        try:
                            adaptive_agent = adaptive_agent or AdaptiveAgent(db)
                            adaptive_agent.generate_overall_roadmap(req_user_id, req_subject, allowed_filenames, force_level="Advanced")
                        except Exception:
                            pass
                    elif current_lvl == "Advanced":
                        roadmap.is_completed = True

        eval_agent = EvaluationAgent(db)
        performance_data = eval_agent.evaluate_performance(
            user_id=req_user_id,
            subject=req_subject,
            current_score=score_percent,
            test_type=final_test_type
        )

        if profile:
            profile.avg_score = performance_data["actual_test_score"]

        progress = db.query(StudentLearningProgress).filter(StudentLearningProgress.user_id == req_user_id).first()
        if not progress:
            progress = StudentLearningProgress(user_id=req_user_id)
            db.add(progress)

        total_tests_count = db.query(StudentDocumentScoreHistory).filter(
            StudentDocumentScoreHistory.user_id == req_user_id,
            StudentDocumentScoreHistory.test_type != "baseline",
        ).count()
        lessons_completed_count = db.query(StudentDocumentEvaluation).filter(
            StudentDocumentEvaluation.user_id == req_user_id,
            StudentDocumentEvaluation.is_completed == True,
        ).count()
        progress.tests_completed_total = int(total_tests_count)
        progress.lessons_completed_total = int(lessons_completed_count)
        progress.last_active_at = datetime.utcnow()

        if req_source_file and target_class:
            related_doc = db.query(Document).filter(
                Document.class_id == target_class.id,
                Document.subject_id == target_class.subject_id,
                Document.filename == str(req_source_file).strip(),
            ).first()
            if related_doc and profile:
                refreshed = compute_subject_score_metrics(
                    db=db,
                    user_id=req_user_id,
                    subject_id=related_doc.subject_id,
                    class_id=related_doc.class_id,
                )
                profile.avg_score = refreshed["test_score"]

        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"⚠️ Post-submit background update failed: {exc}")
    finally:
        db.close()


# --- SCHEMA ---
class QuizRequest(BaseModel):
    subject: str 
    user_id: int 

# Thêm Schema cho Bài kiểm tra cuối buổi
class SessionQuizRequest(BaseModel):
    subject: str
    user_id: int
    session_topic: str  # Tên bài học (VD: "Cấu trúc dữ liệu mảng")
    level: str          # Trình độ (VD: "Intermediate")
    source_file: Optional[str] = None

class AnswerSubmission(BaseModel):
    question_id: int
    selected_option: str 

class SaveQuizResultRequest(BaseModel):
    """Schema để save quiz result + call EvaluationAgent"""
    subject: str
    user_id: int
    source_file: str  # Tên file tài liệu đã test
    answers: List[AnswerSubmission]  # [{question_id, selected_option}]
    total_questions: int = 15  # Mặc định 15 câu/chương

class DocumentQuestionBankRequest(BaseModel):
    subject: str
    user_id: int
    source_file: str
    target_count: int = 20

class SubmitRequest(BaseModel):
    subject: str
    user_id: int 
    answers: List[AnswerSubmission]
    duration_seconds: int = 300 
    is_session_quiz: bool = False
    test_type: str = "baseline" 
    session_topic: Optional[str] = None
    session_number: Optional[int] = None
    source_file: Optional[str] = None

# --- 1. SINH ĐỀ THI ĐÁNH GIÁ TỔNG QUAN (ĐẦU VÀO) ---
@router.post("/generate")
def generate_quiz(req: QuizRequest, db: Session = Depends(get_db)):
    logger.info("generate_quiz start user_id=%s subject=%s", req.user_id, req.subject)
    if not req.subject or req.subject.strip() == "":
        raise HTTPException(status_code=400, detail="Vui lòng chọn môn học!")

    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Người dùng không tồn tại.")

    # TÌM LỚP HỌC MÀ SINH VIÊN ĐÃ THAM GIA ĐÚNG VỚI MÔN NÀY
    target_class = next((c for c in getattr(user, 'enrolled_classes', []) if c.subject == req.subject), None)
    if not target_class:
        raise HTTPException(status_code=400, detail=f"Bạn chưa tham gia lớp học nào cho môn '{req.subject}'.")

    # Cho phép làm lại bài đánh giá đầu vào bất cứ lúc nào, không khóa theo roadmap.

    # LẤY TÀI LIỆU CỦA ĐÚNG LỚP ĐÓ - DÙNG SUBJECT_ID FK THAY VÌ SUBJECT STRING
    subject_id = int(target_class.subject_id)
    allowed_docs = db.query(Document).filter(
        Document.class_id == target_class.id,
        Document.subject_id == target_class.subject_id
    ).all()
    
    allowed_filenames = [doc.filename for doc in allowed_docs]

    if not allowed_filenames:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Lớp học của bạn hiện chưa có tài liệu cho môn '{req.subject}'."
        )

    # Gọi AssessmentAgent với cấu hình cực kỳ nghiêm ngặt
    agent = AssessmentAgent(db)
    questions = agent.get_or_create_quiz(
        subject=req.subject, 
        user_id=req.user_id, 
        num_questions=20, 
        allowed_files=allowed_filenames
    )
    
    if not questions:
        raise HTTPException(status_code=404, detail="AI chưa chuẩn bị xong câu hỏi. Hãy thử lại!")
        
    logger.info("generate_quiz done user_id=%s subject=%s question_count=%s", req.user_id, req.subject, len(questions))
    return {"questions": questions, "subject": req.subject}

# --- 2. TẠO BÀI KIỂM TRA THEO BÁM SÁT BUỔI HỌC VÀ LEVEL ---
@router.post("/generate-session")
def generate_session_assessment(req: SessionQuizRequest, db: Session = Depends(get_db)):
    logger.info(
        "generate_session start user_id=%s subject=%s session_topic=%s source_file=%s",
        req.user_id,
        req.subject,
        req.session_topic,
        req.source_file,
    )
    if not req.subject or not req.session_topic:
        raise HTTPException(status_code=400, detail="Thiếu thông tin môn học hoặc chủ đề.")

    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Người dùng không hợp lệ.")

    # TÌM LỚP HỌC MÀ SINH VIÊN ĐÃ THAM GIA ĐÚNG VỚI MÔN NÀY
    target_class = next((c for c in getattr(user, 'enrolled_classes', []) if c.subject == req.subject), None)
    if not target_class:
        raise HTTPException(status_code=400, detail=f"Bạn chưa tham gia lớp học nào cho môn '{req.subject}'.")

    # LẤY TÀI LIỆU CỦA ĐÚNG LỚP ĐÓ - DÙNG SUBJECT_ID FK THAY VÌ SUBJECT STRING
    allowed_docs = db.query(Document).filter(
        Document.class_id == target_class.id,
        Document.subject_id == target_class.subject_id
    ).all()
    allowed_filenames = [doc.filename for doc in allowed_docs]
    subject_id = int(target_class.subject_id)

    requested_file = (req.source_file or "").strip()
    if requested_file and requested_file in allowed_filenames:
        allowed_filenames = [requested_file]

    # Gọi Agent tạo đề thi bám sát Topic và Level
    agent = AdaptiveAgent(db)
    raw_questions = agent.generate_session_quiz(
        subject=req.subject,
        session_topic=req.session_topic,
        level=req.level,
        allowed_filenames=allowed_filenames
    )
    
    if not raw_questions:
        raise HTTPException(status_code=500, detail="AI đang bận, không thể tạo đề thi lúc này. Hãy thử lại!")

    # Lưu câu hỏi AI vừa tạo vào Database để hàm /submit có thể chấm điểm được
    saved_questions = []
    pending_questions = []
    for q_data in raw_questions:
        new_q = QuestionBank(
            subject_id=subject_id,
            subject=req.subject,
            content=q_data.get("content", ""),
            options=json.dumps(q_data.get("options", []), ensure_ascii=False),
            correct_answer=q_data.get("correct_label", "A"), 
            explanation=q_data.get("explanation", ""),
            difficulty=req.level 
        )
        db.add(new_q)
        db.flush()
        pending_questions.append((new_q, q_data))

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "generate_session save failed user_id=%s subject=%s session_topic=%s",
            req.user_id,
            req.subject,
            req.session_topic,
        )
        raise

    for new_q, q_data in pending_questions:
        saved_questions.append({
            "id": new_q.id,
            "content": new_q.content,
            "options": q_data.get("options", [])
        })
        
    logger.info(
        "generate_session done user_id=%s subject=%s saved_questions=%s source_file=%s",
        req.user_id,
        req.subject,
        len(saved_questions),
        requested_file or "",
    )
    return {
        "questions": saved_questions,
        "subject": req.subject,
        "min_pass_correct": 4,
        "source_file": requested_file or None,
    }


@router.post("/ensure-document-question-bank")
def ensure_document_question_bank(req: DocumentQuestionBankRequest, db: Session = Depends(get_db)):
    if not req.subject or not req.source_file:
        raise HTTPException(status_code=400, detail="Cần chỉ định môn học (subject) và tên file tài liệu (source_file)")

    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Người dùng không hợp lệ.")

    target_class = next((c for c in getattr(user, 'enrolled_classes', []) if c.subject == req.subject), None)
    if not target_class:
        raise HTTPException(status_code=400, detail=f"Bạn chưa tham gia lớp học nào cho môn '{req.subject}'.")

    doc = db.query(Document).filter(
        Document.class_id == target_class.id,
        Document.filename == req.source_file.strip()
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu '{req.source_file}' trong lớp học của bạn.")

    requested_file = req.source_file.strip()
    existing_count = db.query(func.count(QuestionBank.id)).filter(
        QuestionBank.subject == req.subject,
        QuestionBank.source_file == requested_file,
    ).scalar() or 0

    generated_count = 0
    missing_count = max(0, int(req.target_count) - int(existing_count))
    if missing_count > 0:
        agent = AssessmentAgent(db)
        generated = agent.pre_generate_questions_for_document(
            subject=req.subject,
            source_file=requested_file,
            count=min(missing_count, 20),
            force_refresh=True,
            replace_existing=False,
        )
        generated_count = len(generated)
        existing_count = db.query(func.count(QuestionBank.id)).filter(
            QuestionBank.subject == req.subject,
            QuestionBank.source_file == requested_file,
        ).scalar() or 0

    return {
        "subject": req.subject,
        "source_file": requested_file,
        "existing_count": int(existing_count),
        "generated_count": int(generated_count),
        "is_ready": int(existing_count) >= req.target_count,
    }

# --- 2B. SINH 15 CÂU TRỰ NGHIỆM THEO CHƯƠNG/TÀI LIỆU ---
@router.post("/generate-chapter-quiz")
def generate_chapter_quiz(req: SessionQuizRequest, db: Session = Depends(get_db)):
    """Sinh 15 câu trắc nghiệm theo một chương (document/source_file) cụ thể.
    Sử dụng AssessmentAgent để đảm bảo content chuyên sâu và diverse."""
    
    if not req.subject or not req.source_file:
        raise HTTPException(status_code=400, detail="Cần chỉ định môn học (subject) và tên file tài liệu (source_file)")

    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Người dùng không hợp lệ.")

    # TÌM LỚP HỌC MÀ SINH VIÊN ĐÃ THAM GIA 
    target_class = next((c for c in getattr(user, 'enrolled_classes', []) if c.subject == req.subject), None)
    if not target_class:
        raise HTTPException(status_code=400, detail=f"Bạn chưa tham gia lớp học nào cho môn '{req.subject}'.")

    # Kiểm tra xem source_file có phải tài liệu của lớp này không
    doc = db.query(Document).filter(
        Document.class_id == target_class.id,
        Document.filename == req.source_file.strip()
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu '{req.source_file}' trong lớp học của bạn.")

    requested_file = req.source_file.strip()
    agent = AssessmentAgent(db)

    # Chỉ đọc các câu hỏi đã được sinh sẵn trong DB lúc upload tài liệu.
    query = db.query(QuestionBank).filter(
        QuestionBank.subject == req.subject,
        QuestionBank.source_file == requested_file,
    )
    existing = query.all()

    missing_count = max(0, 15 - len(existing))
    if missing_count > 0:
        agent.pre_generate_questions_for_document(
            subject=req.subject,
            source_file=requested_file,
            count=missing_count,
            force_refresh=True,
            replace_existing=False,
        )
        existing = query.all()

    if not existing:
        raise HTTPException(status_code=404, detail="Chưa có bộ câu hỏi đã sinh sẵn cho tài liệu này. Vui lòng để giảng viên upload hoặc làm mới tài liệu.")
    
    questions = existing
    if len(existing) >= 15:
        # Đã có sẵn, chỉ cần random 15 câu và trả về
        questions = query.order_by(func.random()).limit(15).all()

    result = []
    for q in questions:
        parsed_options = _normalize_question_bank_options(q.options)

        result.append({
            "id": q.id,
            "content": _sanitize_question_bank_text(q.content),
            "options": parsed_options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation
        })
    
    return {
        "questions": result,
        "subject": req.subject,
        "source_file": req.source_file,
        "min_pass_correct": max(1, round(len(result) * 0.33)),
        "total_questions": len(result)
    }

# --- 3. NỘP BÀI, CHẤM ĐIỂM & ĐIỀU HƯỚNG LỘ TRÌNH (THĂNG CẤP) ---
@router.post("/submit")
def submit_quiz(req: SubmitRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    logger.info(
        "submit_quiz start user_id=%s subject=%s answers=%s source_file=%s is_session_quiz=%s",
        req.user_id,
        req.subject,
        len(req.answers or []),
        req.source_file,
        req.is_session_quiz,
    )
    if not req.answers:
        raise HTTPException(status_code=400, detail="Không có câu trả lời nào.")

    subject_id = get_subject_id(req.subject, db)
    user_map = {a.question_id: a.selected_option for a in req.answers}
    question_ids = list(user_map.keys())

    profile = db.query(LearnerProfile).filter_by(subject_id=subject_id, user_id=req.user_id).first()
    if not profile:
        profile = db.query(LearnerProfile).filter_by(subject=req.subject, user_id=req.user_id).first()
    old_level = profile.current_level if profile else "Beginner"

    questions_db = db.query(QuestionBank).filter(
        QuestionBank.id.in_(question_ids),
        QuestionBank.subject == req.subject
    ).all()

    correct_count = 0
    wrong_questions_log = []
    detailed_results = []

    for q in questions_db:
        user_choice = user_map.get(q.id, "")
        db_correct_label = q.correct_answer.strip().upper() if q.correct_answer else ""
        if len(db_correct_label) > 1:
            match_db = re.search(r'^(?:ĐÁP ÁN\s*|CHỌN\s*)?([A-D])\s*[\.\:\-\)]', db_correct_label, re.IGNORECASE)
            db_correct_label = match_db.group(1).upper() if match_db else db_correct_label[0].upper()

        user_label = user_choice.strip().upper() if user_choice else ""
        is_correct = (user_label == db_correct_label)
        if is_correct:
            correct_count += 1
        else:
            wrong_questions_log.append({
                "question": _sanitize_question_bank_text(q.content),
                "student_choice": user_choice,
                "correct_answer": q.correct_answer,
                "options": _normalize_question_bank_options(q.options),
                "explanation": q.explanation,
                "question_bank_id": q.id,
            })

        detailed_results.append({
            "question_id": q.id,
            "is_correct": is_correct,
            "explanation": q.explanation,
            "correct_label": db_correct_label
        })

    total_q = len(questions_db)
    score_percent = round((correct_count / total_q * 100), 2) if total_q > 0 else 0.0

    profiler = ProfilingAgent(db)
    calculated_level = profiler.classify_learner(correct_count, total_q, req.subject, req.user_id)
    new_level = old_level if req.is_session_quiz else calculated_level

    roadmap = db.query(LearningRoadmap).filter_by(user_id=req.user_id, subject_id=subject_id).first()
    if not roadmap:
        roadmap = db.query(LearningRoadmap).filter_by(user_id=req.user_id, subject=req.subject).first()

    is_passed = True
    msg = ""
    chapter_feedback = None
    needs_background_roadmap = False
    pending_force_level = None

    user_obj = db.query(User).filter(User.id == req.user_id).first()
    target_class = next((c for c in getattr(user_obj, 'enrolled_classes', []) if c.subject == req.subject), None)

    if not roadmap:
        needs_background_roadmap = True
        pending_force_level = new_level
        msg = f"Đã ghi nhận điểm số. Hệ thống đang cập nhật lộ trình học dựa trên trình độ {new_level} của bạn."
    else:
        total_sessions = len(roadmap.roadmap_data) if roadmap.roadmap_data else 11
        if req.is_session_quiz:
            required_correct = 4
            is_passed = correct_count >= required_correct
            if is_passed:
                if req.session_number and req.session_number != roadmap.current_session:
                    msg = "Bạn đã hoàn thành bài kiểm tra của buổi này. Hãy tiếp tục theo buổi hiện tại trên lộ trình."
                elif roadmap.current_session < total_sessions:
                    roadmap.current_session += 1
                    msg = "Chúc mừng! Bạn đã qua bài và mở khóa chapter tiếp theo."
                else:
                    roadmap.is_completed = True
                    msg = "Tuyệt vời! Bạn đã hoàn thành chapter cuối cùng của lộ trình hiện tại."
                chapter_feedback = {
                    "is_session_quiz": True,
                    "required_correct": required_correct,
                    "passed": True,
                    "weak_topics": [],
                    "session_topic": req.session_topic,
                    "source_file": req.source_file,
                }
            else:
                weak_topics = [item.get("question", "")[:120] for item in wrong_questions_log[:3] if item.get("question")]
                msg = (
                    f"Bạn mới đúng {correct_count}/{total_q} câu. Cần tối thiểu {required_correct} câu để qua chapter. "
                    "Hệ thống đã gợi ý phần cần ôn để bạn học lại và làm lại bài."
                )
                chapter_feedback = {
                    "is_session_quiz": True,
                    "required_correct": required_correct,
                    "passed": False,
                    "weak_topics": weak_topics,
                    "session_topic": req.session_topic,
                    "source_file": req.source_file,
                }
        elif score_percent >= 60.0:
            is_passed = True
            if roadmap.current_session < total_sessions:
                roadmap.current_session += 1
                msg = "Chúc mừng! Bạn đã mở khóa bài học tiếp theo."
            else:
                current_lvl = roadmap.level_assigned
                if current_lvl == "Beginner":
                    roadmap.level_assigned = "Intermediate"
                    roadmap.current_session = 1
                    new_level = "Intermediate"
                    if profile:
                        profile.current_level = "Intermediate"
                    needs_background_roadmap = True
                    pending_force_level = "Intermediate"
                    msg = "Bạn đã thăng cấp INTERMEDIATE. Hệ thống đang cập nhật lộ trình mới."
                elif current_lvl == "Intermediate":
                    roadmap.level_assigned = "Advanced"
                    roadmap.current_session = 1
                    new_level = "Advanced"
                    if profile:
                        profile.current_level = "Advanced"
                    needs_background_roadmap = True
                    pending_force_level = "Advanced"
                    msg = "Bạn đã thăng cấp ADVANCED. Hệ thống đang cập nhật lộ trình mới."
                elif current_lvl == "Advanced":
                    roadmap.is_completed = True
                    msg = "Bạn đã hoàn thành toàn bộ lộ trình học hiện tại."
        else:
            is_passed = False
            msg = "Điểm chưa đạt (cần tối thiểu 60%). Hãy ôn tập lại toàn bộ kiến thức và thử lại nhé!"

    final_test_type = "session" if req.is_session_quiz and req.test_type == "baseline" else req.test_type

    history = AssessmentHistory(
        subject_id=subject_id,
        subject=req.subject,
        user_id=req.user_id,
        score=score_percent,
        test_type=final_test_type,
        level_at_time=new_level,
        duration_seconds=req.duration_seconds,
        correct_count=correct_count,
        total_questions=total_q,
        wrong_detail=json.dumps(wrong_questions_log, ensure_ascii=False),
        timestamp=datetime.utcnow()
    )
    db.add(history)

    if req.source_file and target_class:
        related_doc = db.query(Document).filter(
            Document.class_id == target_class.id,
            Document.subject_id == target_class.subject_id,
            Document.filename == req.source_file.strip(),
        ).first()
        if related_doc:
            doc_eval = db.query(StudentDocumentEvaluation).filter(
                StudentDocumentEvaluation.user_id == req.user_id,
                StudentDocumentEvaluation.document_id == related_doc.id,
            ).first()
            if not doc_eval:
                doc_eval = StudentDocumentEvaluation(
                    user_id=req.user_id,
                    document_id=related_doc.id,
                    subject_id=related_doc.subject_id,
                    class_id=related_doc.class_id,
                    latest_score=0.0,
                    attempts=0,
                    is_completed=False,
                )
                db.add(doc_eval)

            doc_eval.attempts = int(doc_eval.attempts or 0) + 1
            doc_eval.latest_score = float(score_percent)
            doc_eval.is_completed = bool(score_percent >= 60.0)
            doc_eval.last_test_at = datetime.utcnow()

            db.add(StudentDocumentScoreHistory(
                user_id=req.user_id,
                document_id=related_doc.id,
                subject_id=related_doc.subject_id,
                class_id=related_doc.class_id,
                score=float(score_percent),
                test_type=final_test_type,
                total_questions=total_q,
                correct_count=correct_count,
                tested_at=datetime.utcnow(),
            ))

            # --- LƯU CÁC CÂU SAI CHO TAB "HỌC TẬP" ---
            if wrong_questions_log:
                for wq in wrong_questions_log:
                    db.add(WrongAnswerRecord(
                        user_id=req.user_id,
                        document_id=related_doc.id,
                        subject_id=subject_id,
                        class_id=target_class.id if target_class else None,
                        question_bank_id=wq.get("question_bank_id"),
                        question_text=wq.get("question", ""),
                        options_json=wq.get("options"),
                        student_choice=wq.get("student_choice", ""),
                        correct_answer=wq.get("correct_answer", ""),
                        explanation=wq.get("explanation"),
                        assessment_history_id=history.id,
                    ))

    progress = db.query(StudentLearningProgress).filter(StudentLearningProgress.user_id == req.user_id).first()
    if not progress:
        progress = StudentLearningProgress(user_id=req.user_id)
        db.add(progress)
    if profile:
        profile.total_tests = int(profile.total_tests or 0) + 1
    total_tests_count = db.query(StudentDocumentScoreHistory).filter(
        StudentDocumentScoreHistory.user_id == req.user_id,
        StudentDocumentScoreHistory.test_type != "baseline",
    ).count()
    lessons_completed_count = db.query(StudentDocumentEvaluation).filter(
        StudentDocumentEvaluation.user_id == req.user_id,
        StudentDocumentEvaluation.is_completed == True,
    ).count()
    progress.tests_completed_total = int(total_tests_count)
    progress.lessons_completed_total = int(lessons_completed_count)
    progress.last_active_at = datetime.utcnow()

    db.commit()

    score_metrics = compute_subject_score_metrics(
        db=db,
        user_id=req.user_id,
        subject_id=subject_id,
        class_id=target_class.id if target_class else None,
    )
    actual_test_score = round(float(score_metrics.get("test_score", score_percent) or score_percent), 2)
    effort_score = _compute_effort_score(db, req.user_id)
    progress_score = round(float(score_metrics.get("progress_score", 0.0) or 0.0), 2)
    final_score = round((0.5 * actual_test_score) + (0.3 * effort_score) + (0.2 * progress_score), 2)
    ai_feedback = _build_fast_feedback(score_percent, is_passed, req.is_session_quiz)

    req_payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    if needs_background_roadmap:
        req_payload["force_level"] = pending_force_level
    if background_tasks is not None:
        background_tasks.add_task(
            _run_post_submit_updates,
            req_payload,
            subject_id,
            old_level,
            final_test_type,
            score_percent,
            correct_count,
            total_q,
        )

    logger.info(
        "submit_quiz done user_id=%s subject=%s score=%s correct_count=%s total_questions=%s passed=%s",
        req.user_id,
        req.subject,
        score_percent,
        correct_count,
        total_q,
        is_passed,
    )
    return {
        "level": new_level,
        "score": score_percent,
        "correct_count": correct_count,
        "total_questions": total_q,
        "results": detailed_results,
        "is_passed": is_passed,
        "message": msg,
        "chapter_feedback": chapter_feedback,
        "actual_test_score": actual_test_score,
        "effort_score": effort_score,
        "progress_score": progress_score,
        "final_score": final_score,
        "ai_feedback": ai_feedback
    }

# --- 4. SAVE QUIZ RESULT + EVALUATION AGENT ANALYSIS ---
@router.post("/save-quiz-result")
def save_quiz_result(req: SaveQuizResultRequest, db: Session = Depends(get_db)):
    """
    Lưu kết quả quiz + gọi EvaluationAgent phân tích từng câu sai chi tiết.
    Dùng cho Quiz page mới - mở tab riêng, sau khi submit bài thì lưu kết quả + phân tích.
    """
    
    if not req.subject or not req.source_file:
        raise HTTPException(status_code=400, detail="Cần subject và source_file để save result")
    
    if not req.answers:
        raise HTTPException(status_code=400, detail="Không có câu trả lời nào")
    
    user = db.query(User).filter(User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Người dùng không hợp lệ")
    
    # Xử lý chấm điểm
    user_map = {a.question_id: a.selected_option for a in req.answers}
    question_ids = list(user_map.keys())
    
    questions_db = db.query(QuestionBank).filter(
        QuestionBank.id.in_(question_ids),
        QuestionBank.subject == req.subject,
        QuestionBank.source_file == req.source_file
    ).all()
    
    correct_count = 0
    question_answer_pairs = []
    
    for q in questions_db:
        user_choice = user_map.get(q.id, "")
        db_correct_label = q.correct_answer.strip().upper() if q.correct_answer else ""
        
        if len(db_correct_label) > 1:
            match_db = re.search(r'^(?:ĐÁP ÁN\s*|CHỌN\s*)?([A-D])\s*[\.\:\-\)]', db_correct_label, re.IGNORECASE)
            db_correct_label = match_db.group(1).upper() if match_db else db_correct_label[0].upper()
        
        user_label = user_choice.strip().upper() if user_choice else ""
        is_correct = (user_label == db_correct_label)
        
        if is_correct:
            correct_count += 1
        
        # Parse options
        parsed_options = _normalize_question_bank_options(q.options)

        question_answer_pairs.append({
            "question_id": q.id,
            "question_text": _sanitize_question_bank_text(q.content),
            "user_answer": user_label,
            "correct_answer": db_correct_label,
            "is_correct": is_correct,
            "options": parsed_options,
            "explanation": q.explanation
        })
    
    total_q = len(questions_db)
    score_percent = round((correct_count / total_q * 100), 2) if total_q > 0 else 0.0
    
    # Gọi EvaluationAgent phân tích từng câu sai
    eval_agent = EvaluationAgent(db)
    analysis_results = eval_agent.analyze_quiz_answers(
        subject=req.subject,
        question_answer_pairs=question_answer_pairs,
        source_file=req.source_file
    )
    
    # Lưu vào AssessmentHistory
    subject_id = get_subject_id(req.subject, db)
    history = AssessmentHistory(
        subject_id=subject_id,
        subject=req.subject,
        user_id=req.user_id,
        score=score_percent,
        test_type="session",  # Luôn lưu dưới dạng session quiz
        level_at_time="Beginner",
        duration_seconds=0,
        correct_count=correct_count,
        total_questions=total_q,
        wrong_detail=json.dumps([p for p in question_answer_pairs if not p["is_correct"]], ensure_ascii=False),
        timestamp=datetime.utcnow()
    )
    db.add(history)

    # Đồng thời lưu theo từng tài liệu để dùng cho điểm môn theo tất cả phần.
    related_doc = db.query(Document).filter(
        Document.subject_id == subject_id,
        Document.filename == req.source_file.strip(),
    ).order_by(Document.upload_time.desc()).first()
    if related_doc:
        doc_eval = db.query(StudentDocumentEvaluation).filter(
            StudentDocumentEvaluation.user_id == req.user_id,
            StudentDocumentEvaluation.document_id == related_doc.id,
        ).first()
        if not doc_eval:
            doc_eval = StudentDocumentEvaluation(
                user_id=req.user_id,
                document_id=related_doc.id,
                subject_id=related_doc.subject_id,
                class_id=related_doc.class_id,
                latest_score=0.0,
                attempts=0,
                is_completed=False,
            )
            db.add(doc_eval)

        doc_eval.attempts = int(doc_eval.attempts or 0) + 1
        doc_eval.latest_score = float(score_percent)
        doc_eval.is_completed = bool(score_percent >= 60.0)
        doc_eval.last_test_at = datetime.utcnow()

        db.add(StudentDocumentScoreHistory(
            user_id=req.user_id,
            document_id=related_doc.id,
            subject_id=related_doc.subject_id,
            class_id=related_doc.class_id,
            score=float(score_percent),
            test_type="session",
            total_questions=total_q,
            correct_count=correct_count,
            tested_at=datetime.utcnow(),
        ))

        # --- LƯU CÁC CÂU SAI CHO TAB "HỌC TẬP" ---
        wrong_pairs = [p for p in question_answer_pairs if not p["is_correct"]]
        if wrong_pairs:
            for wp in wrong_pairs:
                db.add(WrongAnswerRecord(
                    user_id=req.user_id,
                    document_id=related_doc.id,
                    subject_id=related_doc.subject_id,
                    class_id=related_doc.class_id,
                    question_bank_id=wp.get("question_id"),
                    question_text=wp.get("question_text", ""),
                    options_json=wp.get("options"),
                    student_choice=wp.get("user_answer", ""),
                    correct_answer=wp.get("correct_answer", ""),
                    explanation=wp.get("explanation"),
                    assessment_history_id=history.id,
                ))

    db.commit()

    is_passed = correct_count >= 5  # Cần 5/15 để pass

    return {
        "score": score_percent,
        "correct_count": correct_count,
        "total_questions": total_q,
        "is_passed": is_passed,
        "min_pass_correct": 5,
        "analysis": analysis_results,  # Chi tiết phân tích từng câu từ EvaluationAgent
        "message": f"Bạn trả lời đúng {correct_count}/{total_q} câu. {'✅ Vượt qua!' if is_passed else '❌ Chưa đạt, hãy làm lại!'}",
        "source_file": req.source_file
    }

# --- CÁC API TRUY VẤN LỊCH SỬ VÀ ROADMAP ---
@router.get("/roadmap/{subject}")
def get_learning_roadmap(subject: str, user_id: int, db: Session = Depends(get_db)):
    subject_obj = db.query(Subject).filter(Subject.name.ilike(subject.strip())).first()
    roadmap = None
    if subject_obj:
        roadmap = db.query(LearningRoadmap).filter_by(user_id=user_id, subject_id=subject_obj.id).first()
    if not roadmap:
        roadmap = db.query(LearningRoadmap).filter_by(subject=subject, user_id=user_id).first()
    if not roadmap:
        return {"has_roadmap": False}
        
    total_sessions = len(roadmap.roadmap_data) if roadmap.roadmap_data else 11
    
    if roadmap.is_completed:
        progress = 100
    else:
        progress = ((roadmap.current_session - 1) / total_sessions) * 100 if total_sessions > 0 else 0
        
    return {
        "has_roadmap": True,
        "level_assigned": roadmap.level_assigned,
        "current_session": roadmap.current_session,
        "is_completed": roadmap.is_completed,
        "roadmap_data": roadmap.roadmap_data, 
        "progress_percent": progress 
    }

@router.get("/history/{subject}")
def get_evaluation_history(subject: str, user_id: int, db: Session = Depends(get_db)):
    history_records = db.query(AssessmentHistory)\
        .filter_by(subject=subject, user_id=user_id)\
        .order_by(AssessmentHistory.timestamp.asc())\
        .all()
    
    if not history_records:
        return {"history": []}
        
    processed_history = []
    previous_score = 0 
    for h in history_records:
        trend = h.score - previous_score
        previous_score = h.score 
        processed_history.append({
            "id": h.id,
            "date": h.timestamp.isoformat(),
            "score": h.score,
            "level": h.level_at_time,
            "duration": h.duration_seconds,
            "trend": trend,
            "test_type": h.test_type, 
            "effort": min(100, int((h.duration_seconds / 300) * 100)) if h.duration_seconds else 0
        })
    processed_history.reverse()
    return {"history": processed_history}

@router.delete("/debug/reset-all")
def reset_database():
    try:
        engine.dispose()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        return {"status": "success", "message": "Đã reset toàn bộ hệ thống!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/all-answers")
def get_all_answers_in_db(db: Session = Depends(get_db)):
    questions = db.query(QuestionBank).all()
    if not questions:
        return {"message": "Database đang trống!"}
    debug_list = []
    for q in questions:
        debug_list.append({
            "id": q.id,
            "mon_hoc": q.subject,
            "cau_hoi": q.content,
            "lua_chon": q.options,
            "dap_an_dung": q.correct_answer,
            "giai_thich": q.explanation
        })
    return {"tong_so_cau": len(debug_list), "danh_sach_chi_tiet": debug_list}
