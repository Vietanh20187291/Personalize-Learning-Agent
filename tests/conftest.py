import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from api.auth import hash_password
from db import models
from db.database import Base, get_db
from memory.conversation_memory import get_conversation_memory


@pytest.fixture(autouse=True)
def clear_conversation_memory():
    memory = get_conversation_memory()
    memory.sessions.clear()
    yield
    memory.sessions.clear()


@pytest.fixture
def db_env(tmp_path):
    db_path = tmp_path / "suite.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    yield SimpleNamespace(
        engine=engine,
        SessionLocal=testing_session_local,
    )

    engine.dispose()


@pytest.fixture
def db_session(db_env):
    db = db_env.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client_factory(db_env):
    def _make(*router_specs, overrides=None):
        app = FastAPI()
        for spec in router_specs:
            if isinstance(spec, tuple):
                router, prefix = spec
                app.include_router(router, prefix=prefix)
            else:
                app.include_router(spec)

        def override_get_db():
            db = db_env.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        if overrides:
            app.dependency_overrides.update(overrides)
        return TestClient(app)

    return _make


@pytest.fixture
def seed():
    def create_subject(db, name="OOP", description=None, icon=None):
        subject = models.Subject(name=name, description=description, icon=icon)
        db.add(subject)
        db.commit()
        db.refresh(subject)
        return subject

    def create_user(db, username, role="student", full_name=None, password="secret123", student_id=None):
        user = models.User(
            username=username,
            hashed_password=hash_password(password),
            role=role,
            full_name=full_name or username,
            student_id=student_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def create_classroom(db, name, subject, teacher, class_code=None):
        classroom = models.Classroom(
            name=name,
            subject_id=subject.id,
            subject=subject.name,
            class_code=class_code or f"CLS-{subject.id}{teacher.id}{len(name)}",
            teacher_id=teacher.id,
        )
        db.add(classroom)
        db.commit()
        db.refresh(classroom)
        return classroom

    def enroll_student(db, student, classroom):
        classroom.students.append(student)
        db.commit()
        db.refresh(classroom)
        db.refresh(student)
        return classroom

    def create_document(
        db,
        subject,
        classroom,
        teacher,
        filename="doc1.pdf",
        title=None,
        visible=True,
        file_path=None,
    ):
        document = models.Document(
            title=title or filename,
            file_path=file_path or f"temp_uploads/{filename}",
            filename=filename,
            subject_id=subject.id,
            subject=subject.name,
            teacher_id=teacher.id if teacher else None,
            class_id=classroom.id if classroom else None,
        )
        db.add(document)
        db.flush()
        db.add(
            models.DocumentPublication(
                doc_id=document.id,
                is_visible_to_students=visible,
            )
        )
        db.commit()
        db.refresh(document)
        return document

    def create_chunk(db, subject, filename, content, classroom=None):
        chunk = models.Chunk(
            content=content,
            subject_id=subject.id,
            subject=subject.name,
            source_file=filename,
            class_id=classroom.id if classroom else None,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)
        return chunk

    def create_question(
        db,
        subject,
        content="Question?",
        options=None,
        correct_answer="A",
        source_file="doc1.pdf",
        difficulty="Medium",
        explanation="Because",
    ):
        question = models.QuestionBank(
            subject_id=subject.id,
            subject=subject.name,
            difficulty=difficulty,
            content=content,
            options=options or ["A. One", "B. Two", "C. Three", "D. Four"],
            correct_answer=correct_answer,
            explanation=explanation,
            source_file=source_file,
        )
        db.add(question)
        db.commit()
        db.refresh(question)
        return question

    def create_roadmap(db, student, subject, level="Beginner", roadmap_data=None, current_session=1):
        roadmap = models.LearningRoadmap(
            user_id=student.id,
            subject_id=subject.id,
            subject=subject.name,
            level_assigned=level,
            roadmap_data=roadmap_data or [{"title": "Session 1"}, {"title": "Session 2"}],
            current_session=current_session,
            is_completed=False,
        )
        db.add(roadmap)
        db.commit()
        db.refresh(roadmap)
        return roadmap

    def create_document_eval(db, student, document, score=20.0, attempts=1, completed=False):
        record = models.StudentDocumentEvaluation(
            user_id=student.id,
            document_id=document.id,
            subject_id=document.subject_id,
            class_id=document.class_id,
            latest_score=score,
            attempts=attempts,
            is_completed=completed,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    return SimpleNamespace(
        subject=create_subject,
        user=create_user,
        classroom=create_classroom,
        enroll=enroll_student,
        document=create_document,
        chunk=create_chunk,
        question=create_question,
        roadmap=create_roadmap,
        document_eval=create_document_eval,
    )
