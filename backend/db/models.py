from sqlalchemy import Column, Integer, String, Float, JSON, ForeignKey, DateTime, Date, Boolean, Text, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base
from datetime import datetime

# --- BẢNG MÔN HỌC ---
class Subject(Base):
    __tablename__ = "subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # Ví dụ: "Toán học", "Tiếng Anh", "Lập trình Python"
    description = Column(String, nullable=True)
    icon = Column(String, nullable=True)  # Có thể lưu emoji hoặc tên icon
    created_at = Column(DateTime, default=datetime.utcnow)

    # Quan hệ với các bảng khác
    classrooms = relationship("Classroom", back_populates="subject_obj")
    documents = relationship("Document", back_populates="subject_obj")
    learning_roadmaps = relationship("LearningRoadmap", back_populates="subject_obj")
    learner_profiles = relationship("LearnerProfile", back_populates="subject_obj")
    study_sessions = relationship("StudySession", back_populates="subject_obj")
    assessment_histories = relationship("AssessmentHistory", back_populates="subject_obj")
    question_banks = relationship("QuestionBank", back_populates="subject_obj")
    chunks = relationship("Chunk", back_populates="subject_obj")
    assessment_results = relationship("AssessmentResult", back_populates="subject_obj")

# --- BẢNG TRUNG GIAN: QUẢN LÝ SINH VIÊN JOIN NHIỀU LỚP ---
enrollment_table = Table(
    "enrollments",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("class_id", Integer, ForeignKey("classrooms.id"), primary_key=True)
)

# --- BẢNG NGƯỜI DÙNG ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="student") 
    full_name = Column(String)
    last_login_at = Column(DateTime, nullable=True)
    
    # MSSV ĐỂ GIÁO VIÊN PHÂN BIỆT SINH VIÊN
    student_id = Column(String, unique=True, index=True, nullable=True)

    managed_classes = relationship("Classroom", back_populates="teacher", foreign_keys="[Classroom.teacher_id]")
    
    # QUAN HỆ N-N: SINH VIÊN VÀ LỚP HỌC
    enrolled_classes = relationship("Classroom", secondary=enrollment_table, back_populates="students")
    
    uploaded_docs = relationship("Document", back_populates="uploader")
    assessment_histories = relationship("AssessmentHistory", back_populates="user")
    roadmaps = relationship("LearningRoadmap", back_populates="user")
    
    # QUAN HỆ ĐỂ TÍNH EFFORT SCORE (THỜI GIAN HỌC)
    study_sessions = relationship("StudySession", back_populates="user")
    login_sessions = relationship("UserLoginSession", back_populates="user")
    orbit_sessions = relationship("OrbitChatSession", back_populates="user")
    orbit_messages = relationship("OrbitChatMessage", back_populates="user")
    learning_plans = relationship("StudentLearningPlan", back_populates="user")
    learning_plan_steps = relationship("StudentLearningPlanStep", back_populates="user")

# --- BẢNG LỚP HỌC ---
class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True) 
    
    # MÔN HỌC VÀ MÃ CODE LỚP HỌC
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED - giữ tạm thời để migrate dữ liệu
    class_code = Column(String, unique=True, index=True)
    
    teacher_id = Column(Integer, ForeignKey("users.id"))

    teacher = relationship("User", back_populates="managed_classes", foreign_keys=[teacher_id])
    subject_obj = relationship("Subject", back_populates="classrooms")
    
    # QUAN HỆ N-N: LỚP HỌC VÀ SINH VIÊN
    students = relationship("User", secondary=enrollment_table, back_populates="enrolled_classes")
    documents = relationship("Document", back_populates="classroom")
    orbit_sessions = relationship("OrbitChatSession", back_populates="classroom")
    orbit_directives = relationship("OrbitCoachDirective", back_populates="classroom")

# --- BẢNG QUẢN LÝ TÀI LIỆU ---
class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)          
    file_path = Column(String)                  
    created_at = Column(DateTime(timezone=True), server_default=func.now()) 
    
    filename = Column(String, index=True) 
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED - giữ tạm thời để migrate dữ liệu
    upload_time = Column(DateTime, default=datetime.utcnow) 
    
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True) 

    uploader = relationship("User", back_populates="uploaded_docs")
    classroom = relationship("Classroom", back_populates="documents")
    subject_obj = relationship("Subject", back_populates="documents")
    publication = relationship("DocumentPublication", back_populates="document", uselist=False, cascade="all, delete-orphan")


class DocumentPublication(Base):
    __tablename__ = "document_publications"

    doc_id = Column(Integer, ForeignKey("documents.id"), primary_key=True)
    is_visible_to_students = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="publication")

# --- BẢNG LỘ TRÌNH HỌC TẬP TỔNG THỂ ---
class LearningRoadmap(Base):
    __tablename__ = "learning_roadmaps"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED - giữ tạm thời để migrate dữ liệu
    
    level_assigned = Column(String) 
    roadmap_data = Column(JSON) 
    
    current_session = Column(Integer, default=1)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="roadmaps")
    subject_obj = relationship("Subject", back_populates="learning_roadmaps")

# --- CÁC BẢNG LƯU TRỮ HỌC TẬP ---
class LearnerProfile(Base):
    __tablename__ = "learner_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED
    current_level = Column(String, default="Beginner") 
    total_tests = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)
    
    subject_obj = relationship("Subject", back_populates="learner_profiles")

# BẢNG NÀY ĐỂ TÍNH EFFORT SCORE (LƯU THỜI GIAN VÀ SỐ PHIÊN HỌC)
class StudySession(Base):
    __tablename__ = "study_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED
    
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, default=0) # Thời gian học thực tế của phiên này
    
    user = relationship("User", back_populates="study_sessions")
    subject_obj = relationship("Subject", back_populates="study_sessions")

class AssessmentHistory(Base):
    __tablename__ = "assessment_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED
    score = Column(Float)
    
    # CỘT NÀY ĐỂ PHÂN BIỆT LOẠI BÀI KIỂM TRA
    # Có thể là: "baseline" (đánh giá đầu vào), "chapter" (bài qua bài), "final" (bài cuối kỳ)
    test_type = Column(String, default="chapter", index=True) 
    
    total_questions = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    wrong_detail = Column(Text, nullable=True) 
    
    level_at_time = Column(String) 
    timestamp = Column(DateTime, default=datetime.utcnow) 
    duration_seconds = Column(Integer)

    user = relationship("User", back_populates="assessment_histories")
    subject_obj = relationship("Subject", back_populates="assessment_histories")

class QuestionBank(Base):
    __tablename__ = "question_bank"
    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED
    difficulty = Column(String, nullable=True) 
    content = Column(String)
    options = Column(JSON) 
    correct_answer = Column(String)
    explanation = Column(Text, nullable=True) 
    is_used = Column(Boolean, default=False)
    source_file = Column(String, index=True, nullable=True)
    
    subject_obj = relationship("Subject", back_populates="question_banks")

class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED
    source_file = Column(String)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)
    
    subject_obj = relationship("Subject", back_populates="chunks")

class AssessmentResult(Base):
    __tablename__ = "assessment_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    subject = Column(String, index=True, nullable=True)  # DEPRECATED
    score = Column(Float)
    wrong_topics = Column(Text, nullable=True) 
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    subject_obj = relationship("Subject", back_populates="assessment_results")


class StudentLearningProgress(Base):
    __tablename__ = "student_learning_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    lessons_completed_total = Column(Integer, default=0)
    tests_completed_total = Column(Integer, default=0)
    total_study_minutes = Column(Integer, default=0)
    total_agent_messages = Column(Integer, default=0)
    total_agent_chat_seconds = Column(Integer, default=0)
    previous_login_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_active_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserLoginSession(Base):
    __tablename__ = "user_login_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    login_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    logout_at = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="login_sessions")


class OrbitChatSession(Base):
    __tablename__ = "orbit_chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, default=datetime.utcnow)
    message_count = Column(Integer, default=0)

    user = relationship("User", back_populates="orbit_sessions")
    classroom = relationship("Classroom", back_populates="orbit_sessions")


class OrbitChatMessage(Base):
    __tablename__ = "orbit_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("orbit_chat_sessions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="orbit_messages")


class OrbitCoachDirective(Base):
    __tablename__ = "orbit_coach_directives"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    target_tests = Column(Integer, default=0)
    target_chapters = Column(Integer, default=0)
    target_documents_json = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    applied_at = Column(DateTime, nullable=True)

    classroom = relationship("Classroom", back_populates="orbit_directives")


class OrbitWeeklyReminderLog(Base):
    __tablename__ = "orbit_weekly_reminder_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    week_start = Column(DateTime, nullable=False, index=True)
    week_end = Column(DateTime, nullable=False)
    email = Column(String, nullable=False)
    status = Column(String, default="sent")
    summary = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class StudentDocumentEvaluation(Base):
    __tablename__ = "student_document_evaluations"
    __table_args__ = (UniqueConstraint("user_id", "document_id", name="uq_user_document_eval"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True, index=True)
    latest_score = Column(Float, default=0.0)
    attempts = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    last_test_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StudentDocumentScoreHistory(Base):
    __tablename__ = "student_document_score_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True, index=True)
    score = Column(Float, nullable=False, default=0.0)
    test_type = Column(String, nullable=False, default="chapter")
    total_questions = Column(Integer, nullable=True)
    correct_count = Column(Integer, nullable=True)
    tested_at = Column(DateTime, default=datetime.utcnow, index=True)


class WrongAnswerRecord(Base):
    """Lưu từng câu trả lời sai của sinh viên theo từng tài liệu."""
    __tablename__ = "wrong_answer_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True, index=True)
    question_bank_id = Column(Integer, ForeignKey("question_bank.id"), nullable=True, index=True)

    question_text = Column(Text, nullable=False)
    options_json = Column(JSON, nullable=True)
    student_choice = Column(String, nullable=True)
    correct_answer = Column(String, nullable=True)
    explanation = Column(Text, nullable=True)

    assessment_history_id = Column(Integer, ForeignKey("assessment_history.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class StudentLearningPlan(Base):
    __tablename__ = "student_learning_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)
    generated_for_login_at = Column(DateTime, nullable=True)
    generation_reason = Column(String, default="login")
    status = Column(String, default="active", index=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="learning_plans")
    steps = relationship("StudentLearningPlanStep", back_populates="plan", cascade="all, delete-orphan")


class StudentLearningPlanStep(Base):
    __tablename__ = "student_learning_plan_steps"
    __table_args__ = (UniqueConstraint("plan_id", "document_id", name="uq_plan_document"),)

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("student_learning_plans.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True, index=True)
    step_order = Column(Integer, nullable=False, index=True)
    planned_date = Column(Date, nullable=False, index=True)
    deadline_date = Column(Date, nullable=True, index=True)
    priority_group = Column(String, default="no_score", index=True)
    latest_score = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    subject_name = Column(String, nullable=True)
    document_title = Column(String, nullable=True)
    document_filename = Column(String, nullable=True)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan = relationship("StudentLearningPlan", back_populates="steps")
    user = relationship("User", back_populates="learning_plan_steps")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    type = Column(String, nullable=False, index=True, default="general")
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class TestOCRExamBatch(Base):
    __tablename__ = "test_ocr_exam_batches"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    class_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    subject_name = Column(String, nullable=False, index=True)
    exam_type = Column(String, nullable=False, default="trac_nghiem")
    level = Column(String, nullable=True)
    num_questions = Column(Integer, nullable=False, default=20)
    num_versions = Column(Integer, nullable=False, default=1)
    batch_code = Column(String, unique=True, nullable=False, index=True)
    generated_docx_path = Column(String, nullable=True)
    answer_key_json = Column(JSON, nullable=False, default=list)
    omr_layout_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class TestOCRGradingRun(Base):
    __tablename__ = "test_ocr_grading_runs"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("test_ocr_exam_batches.id"), nullable=False, index=True)
    uploaded_pdf_path = Column(String, nullable=True)
    page_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class TestOCRGradingResult(Base):
    __tablename__ = "test_ocr_grading_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("test_ocr_grading_runs.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("test_ocr_exam_batches.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False, default=1)
    source_image_path = Column(String, nullable=True)
    student_name_image_path = Column(String, nullable=True)
    detected_student_id = Column(String, nullable=True, index=True)
    detected_exam_code = Column(String, nullable=True, index=True)
    detected_answers_json = Column(JSON, nullable=False, default=list)
    correct_count = Column(Integer, nullable=False, default=0)
    total_questions = Column(Integer, nullable=False, default=0)
    score = Column(Float, nullable=False, default=0.0)
    grading_status = Column(String, nullable=False, default="pending", index=True)
    debug_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ResearchEvaluationCase(Base):
    __tablename__ = "research_evaluation_cases"

    id = Column(Integer, primary_key=True, index=True)
    component = Column(String, nullable=False, index=True)
    agent_key = Column(String, nullable=True, index=True)
    suite_key = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    dataset_name = Column(String, nullable=True, index=True)
    input_json = Column(JSON, nullable=False, default=dict)
    expected_output_text = Column(Text, nullable=True)
    expected_json = Column(JSON, nullable=True)
    evaluation_config_json = Column(JSON, nullable=False, default=dict)
    ground_truth_json = Column(JSON, nullable=True)
    source_reference = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchExperimentRun(Base):
    __tablename__ = "research_experiment_runs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    component = Column(String, nullable=False, index=True)
    agent_key = Column(String, nullable=True, index=True)
    suite_key = Column(String, nullable=True, index=True)
    dataset_name = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    config_json = Column(JSON, nullable=False, default=dict)
    metrics_json = Column(JSON, nullable=True)
    summary_json = Column(JSON, nullable=True)
    rq_summary_json = Column(JSON, nullable=True)
    report_markdown = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ResearchExperimentItemResult(Base):
    __tablename__ = "research_experiment_item_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("research_experiment_runs.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("research_evaluation_cases.id"), nullable=True, index=True)
    component = Column(String, nullable=False, index=True)
    agent_key = Column(String, nullable=True, index=True)
    case_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    input_json = Column(JSON, nullable=False, default=dict)
    output_json = Column(JSON, nullable=True)
    metrics_json = Column(JSON, nullable=True)
    token_usage_json = Column(JSON, nullable=True)
    latency_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ResearchReportSnapshot(Base):
    __tablename__ = "research_report_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    scope = Column(String, nullable=False, default="chapter5", index=True)
    component = Column(String, nullable=True, index=True)
    run_ids_json = Column(JSON, nullable=False, default=list)
    summary_json = Column(JSON, nullable=True)
    markdown_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
