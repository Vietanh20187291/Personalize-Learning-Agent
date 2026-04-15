from sqlalchemy import Column, Integer, String, Float, JSON, ForeignKey, DateTime, Boolean, Text, Table
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
    orbit_sessions = relationship("OrbitChatSession", back_populates="user")
    orbit_messages = relationship("OrbitChatMessage", back_populates="user")

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
    is_visible_to_students = Column(Boolean, default=False, nullable=False)
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
    note = Column(Text, nullable=True)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

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