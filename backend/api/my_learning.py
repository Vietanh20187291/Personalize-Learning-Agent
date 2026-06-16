"""
API module: My Learning – Tab "Học tập" cho sinh viên.
Cung cấp endpoints xem môn học, tài liệu, câu sai, và sinh tài liệu ôn tập.
"""
import os
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq

from db.database import get_db
from db.models import (
    User, Classroom, Subject, Document,
    StudentDocumentEvaluation, DocumentPublication,
    WrongAnswerRecord, StudentLearningProgress,
    StudySession, LearnerProfile,
)
from agents.review_agent import ReviewAgent

load_dotenv()

router = APIRouter()


# ------------------------------------------------------------------ #
#  Schemas                                                            #
# ------------------------------------------------------------------ #
class GenerateReviewRequest(BaseModel):
    user_id: int
    document_id: int


# ------------------------------------------------------------------ #
#  1. GET /api/my-learning/subjects                                   #
#  Trả về tất cả môn học + tài liệu + điểm + số câu sai             #
# ------------------------------------------------------------------ #
@router.get("/subjects")
def get_my_subjects(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")

    enrolled_classes = getattr(user, "enrolled_classes", [])
    if not enrolled_classes:
        return {"subjects": []}

    # Gom lớp theo subject_id
    subject_map: dict[int, dict] = {}  # subject_id -> {subject_name, class_id, ...}

    for classroom in enrolled_classes:
        subject_obj = db.query(Subject).filter(Subject.id == classroom.subject_id).first()
        if not subject_obj:
            continue

        sid = subject_obj.id
        if sid not in subject_map:
            subject_map[sid] = {
                "subject_id": sid,
                "subject_name": subject_obj.name,
                "subject_icon": subject_obj.icon,
                "class_id": classroom.id,
                "class_name": classroom.name,
                "documents": [],
            }

        # Lấy tài liệu của lớp, chỉ hiện tài liệu visible
        docs_query = (
            db.query(Document)
            .outerjoin(DocumentPublication, DocumentPublication.doc_id == Document.id)
            .filter(
                Document.class_id == classroom.id,
                Document.subject_id == classroom.subject_id,
            )
        )
        # Lọc visible: nếu không có publication record thì mặc định visible
        all_docs = docs_query.all()

        for doc in all_docs:
            # Kiểm tra visibility
            pub = (
                db.query(DocumentPublication)
                .filter(DocumentPublication.doc_id == doc.id)
                .first()
            )
            if pub and not pub.is_visible_to_students:
                continue

            # Điểm của sinh viên cho tài liệu này
            doc_eval = (
                db.query(StudentDocumentEvaluation)
                .filter(
                    StudentDocumentEvaluation.user_id == user_id,
                    StudentDocumentEvaluation.document_id == doc.id,
                )
                .first()
            )

            # Đếm số câu sai
            wrong_count = (
                db.query(func.count(WrongAnswerRecord.id))
                .filter(
                    WrongAnswerRecord.user_id == user_id,
                    WrongAnswerRecord.document_id == doc.id,
                )
                .scalar() or 0
            )

            subject_map[sid]["documents"].append({
                "document_id": doc.id,
                "title": doc.title or doc.filename,
                "filename": doc.filename,
                "latest_score": float(doc_eval.latest_score) if doc_eval and doc_eval.latest_score is not None else None,
                "attempts": int(doc_eval.attempts or 0) if doc_eval else 0,
                "is_completed": bool(doc_eval.is_completed) if doc_eval else False,
                "last_test_at": doc_eval.last_test_at.isoformat() if doc_eval and doc_eval.last_test_at else None,
                "wrong_answer_count": int(wrong_count),
            })

    return {"subjects": list(subject_map.values())}


# ------------------------------------------------------------------ #
#  2. GET /api/my-learning/documents/{document_id}/wrong-answers      #
#  Trả về danh sách câu sai của sinh viên cho 1 tài liệu            #
# ------------------------------------------------------------------ #
@router.get("/documents/{document_id}/wrong-answers")
def get_wrong_answers(document_id: int, user_id: int, db: Session = Depends(get_db)):
    # Kiểm tra document tồn tại
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    # Kiểm tra sinh viên có quyền truy cập (enrolled trong lớp chứa tài liệu)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")

    enrolled_class_ids = {c.id for c in getattr(user, "enrolled_classes", [])}
    if doc.class_id and doc.class_id not in enrolled_class_ids:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem tài liệu này.")

    # Lấy tất cả câu sai, ưu tiên lần mới nhất
    records = (
        db.query(WrongAnswerRecord)
        .filter(
            WrongAnswerRecord.user_id == user_id,
            WrongAnswerRecord.document_id == document_id,
        )
        .order_by(WrongAnswerRecord.created_at.desc())
        .all()
    )

    wrong_answers = []
    for r in records:
        wrong_answers.append({
            "id": r.id,
            "question_text": r.question_text or "",
            "options": r.options_json,
            "student_choice": r.student_choice or "",
            "correct_answer": r.correct_answer or "",
            "explanation": r.explanation,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "document_id": document_id,
        "document_title": doc.title or doc.filename,
        "wrong_answers": wrong_answers,
        "total": len(wrong_answers),
    }


# ------------------------------------------------------------------ #
#  3. POST /api/my-learning/generate-review                           #
#  Gửi câu sai cho Groq để sinh tài liệu ôn tập                     #
# ------------------------------------------------------------------ #
@router.post("/generate-review")
def generate_review(req: GenerateReviewRequest, db: Session = Depends(get_db)):
    # Lấy tất cả câu sai cho tài liệu này
    records = (
        db.query(WrongAnswerRecord)
        .filter(
            WrongAnswerRecord.user_id == req.user_id,
            WrongAnswerRecord.document_id == req.document_id,
        )
        .order_by(WrongAnswerRecord.created_at.desc())
        .all()
    )

    if not records:
        raise HTTPException(status_code=404, detail="Không có câu sai nào để ôn tập.")

    # Kiểm tra document
    doc = db.query(Document).filter(Document.id == req.document_id).first()
    doc_title = doc.title or doc.filename if doc else "Tài liệu"

    # Chuẩn bị dữ liệu cho ReviewAgent
    wrong_answers = []
    for r in records:
        wrong_answers.append({
            "question_text": r.question_text or "",
            "options": r.options_json or [],
            "student_choice": r.student_choice or "",
            "correct_answer": r.correct_answer or "",
            "explanation": r.explanation or "",
        })

    # Gọi ReviewAgent
    agent = ReviewAgent()
    review_content = agent.generate_review(wrong_answers)

    return {
        "document_id": req.document_id,
        "document_title": doc_title,
        "wrong_answer_count": len(records),
        "review_content": review_content,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ------------------------------------------------------------------ #
#  4. GET /api/my-learning/ai-insights                                #
#  Sinh nhận xét AI cá nhân hóa cho sinh viên                        #
# ------------------------------------------------------------------ #
@router.get("/ai-insights")
def get_ai_insights(user_id: int, db: Session = Depends(get_db)):
    """Sinh nhận xét AI cá nhân hóa dựa trên toàn bộ dữ liệu học tập."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")

    student_name = (user.full_name or user.username or "bạn").strip()
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # ---- Thu thập dữ liệu ----
    enrolled_classes = list(getattr(user, "enrolled_classes", []) or [])

    # 1. Điểm theo môn
    subject_stats = []
    for classroom in enrolled_classes:
        subject_obj = db.query(Subject).filter(Subject.id == classroom.subject_id).first()
        if not subject_obj:
            continue

        evals = db.query(StudentDocumentEvaluation).filter(
            StudentDocumentEvaluation.user_id == user_id,
            StudentDocumentEvaluation.subject_id == subject_obj.id,
        ).all()

        if not evals:
            subject_stats.append({
                "subject": subject_obj.name,
                "avg_score": None,
                "tests": 0,
                "weak_docs": [],
            })
            continue

        scores = [float(e.latest_score or 0) for e in evals if int(e.attempts or 0) > 0]
        avg = sum(scores) / len(scores) if scores else None

        weak = []
        for e in evals:
            if int(e.attempts or 0) > 0 and float(e.latest_score or 100) < 50:
                doc = db.query(Document).filter(Document.id == e.document_id).first()
                weak.append(doc.title or doc.filename or f"ID {e.document_id}")

        subject_stats.append({
            "subject": subject_obj.name,
            "avg_score": round(avg, 1) if avg is not None else None,
            "tests": sum(int(e.attempts or 0) for e in evals),
            "weak_docs": weak[:5],
        })

    # 2. Thời gian học
    total_study = sum(
        int(s.duration_minutes or 0)
        for s in db.query(StudySession).filter(StudySession.user_id == user_id).all()
    )
    week_study = sum(
        int(s.duration_minutes or 0)
        for s in db.query(StudySession).filter(
            StudySession.user_id == user_id,
            StudySession.start_time >= week_ago,
        ).all()
    )

    # 3. Câu sai gần đây (top 5 topics)
    recent_wrongs = db.query(WrongAnswerRecord).filter(
        WrongAnswerRecord.user_id == user_id,
    ).order_by(WrongAnswerRecord.created_at.desc()).limit(15).all()

    wrong_topics = []
    for w in recent_wrongs[:5]:
        snippet = (w.question_text or "")[:60]
        if snippet:
            wrong_topics.append(snippet)

    # 4. Learner Profile
    learner_level = "chưa xác định"
    if subject_stats:
        main_subject = subject_stats[0]
        profile = db.query(LearnerProfile).filter(
            LearnerProfile.user_id == user_id,
        ).first()
        if profile and profile.current_level:
            learner_level = profile.current_level

    # 5. Last activity
    progress = db.query(StudentLearningProgress).filter_by(user_id=user_id).first()
    days_inactive = None
    if progress and progress.last_active_at:
        days_inactive = (now - progress.last_active_at).days

    # ---- Gọi LLM ----
    data_summary = json.dumps({
        "student_name": student_name,
        "learner_level": learner_level,
        "total_study_minutes": total_study,
        "week_study_minutes": week_study,
        "days_inactive": days_inactive,
        "subjects": subject_stats,
        "recent_wrong_topics": wrong_topics,
    }, ensure_ascii=False, indent=2)

    prompt = f"""Bạn là AI phân tích học tập. Dựa trên dữ liệu thực tế của sinh viên, viết nhận xét cá nhân hóa.

### DỮ LIỆU THỰC TẾ:
{data_summary}

### YÊU CẦU ĐẦU RA (JSON hợp lệ):
{{
  "summary": "1-2 câu tóm tắt tổng quan (gọi tên {{student_name}})",
  "strengths": ["điểm mạnh 1", "điểm mạnh 2"],
  "weaknesses": ["điểm yếu 1", "điểm yếu 2"],
  "recommendations": ["đề xuất cụ thể 1", "đề xuất cụ thể 2", "đề xuất cụ thể 3"],
  "study_pattern": "nhận xét về thói quen học (ví dụ: học dồn cuối tuần, hay học đêm...)",
  "motivation": "1 câu động viên hoặc nhắc nhở cá nhân hóa"
}}

### QUY TẮC:
- Phải CỤ THỂ: chỉ đúng môn, đúng điểm, đúng tài liệu — KHÔNG nói chung chung.
- Nếu có điểm yếu → đề xuất ôn lại tài liệu CỤ THỂ (nếu có tên tài liệu trong weak_docs).
- Nếu nghỉ lâu → nhắc nhở nhẹ nhàng.
- Nếu tốt → khen và đề xuất nâng cao.
- Viết bằng tiếng Việt.
"""

    # Resolve Groq key
    api_key = ""
    for env_name in ["GROQ_KEY_ADAPTIVE", "GROQ_API_KEY", "GROQ_KEY_DEBUG"]:
        value = (os.getenv(env_name) or "").strip()
        if value and not any(t in value.lower() for t in ("dummy", "testing", "placeholder")):
            api_key = value
            break

    if not api_key:
        return _build_fallback_insights(student_name, learner_level, total_study, week_study, subject_stats, days_inactive, wrong_topics)

    try:
        client = Groq(api_key=api_key, timeout=18.0)
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Output valid JSON only. Write in Vietnamese."},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.4,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or "{}"
        data = json.loads(raw)

        return {
            "insights": {
                "summary": data.get("summary", ""),
                "strengths": data.get("strengths", []),
                "weaknesses": data.get("weaknesses", []),
                "recommendations": data.get("recommendations", []),
                "study_pattern": data.get("study_pattern", ""),
                "motivation": data.get("motivation", ""),
            }
        }
    except Exception as exc:
        print(f"⚠️ AI Insights LLM fallback: {exc}")
        return _build_fallback_insights(student_name, learner_level, total_study, week_study, subject_stats, days_inactive, wrong_topics)


def _build_fallback_insights(student_name, learner_level, total_study, week_study, subject_stats, days_inactive, wrong_topics):
    """Fallback insights khi LLM không khả dụng."""
    strengths = []
    weaknesses = []
    recommendations = []

    for s in subject_stats:
        if s["avg_score"] is not None:
            if s["avg_score"] >= 70:
                strengths.append(f"{s['subject']}: điểm TB {s['avg_score']}")
            elif s["avg_score"] < 50:
                weaknesses.append(f"{s['subject']}: điểm TB {s['avg_score']}")
                if s.get("weak_docs"):
                    recommendations.append(f"Ôn lại {', '.join(s['weak_docs'][:2])} của môn {s['subject']}")
            else:
                strengths.append(f"{s['subject']}: ổn ở mức {s['avg_score']}")

    if not strengths:
        strengths = ["Chưa có đủ dữ liệu để đánh giá"]
    if not weaknesses:
        weaknesses = ["Chưa phát hiện điểm yếu rõ rệt"]
    if not recommendations:
        recommendations = ["Tiếp tục duy trì nhịp học hiện tại"]

    inactive_msg = ""
    if days_inactive and days_inactive >= 7:
        inactive_msg = f"Đã {days_inactive} ngày không hoạt động — cần quay lại ngay!"
    elif days_inactive and days_inactive >= 3:
        inactive_msg = f"Đã {days_inactive} ngày chưa học — nên vào hệ thống thường xuyên hơn."

    return {
        "insights": {
            "summary": f"Xin chào {student_name}! Bạn đang ở mức {learner_level}, đã học tổng {total_study} phút.",
            "strengths": strengths[:3],
            "weaknesses": weaknesses[:3],
            "recommendations": recommendations[:4],
            "study_pattern": f"Tuần này học {week_study} phút, tổng {total_study} phút. {'Cần tăng cường.' if week_study < 60 else 'Nhịp học ổn.'}",
            "motivation": inactive_msg or "Tiếp tục giữ vững phong độ học tập nhé!",
        }
    }

