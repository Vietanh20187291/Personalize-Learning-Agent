import io

from api import research
from agents.adaptive_agent import AdaptiveAgent
from db import models
from services.test_ocr_service import TestOCRService as OCRServiceUnderTest


def _seed_research_data(db_session, seed):
    teacher = seed.user(db_session, "teacher.research@example.com", role="teacher", full_name="Research Teacher")
    student = seed.user(db_session, "student.research@example.com", role="student", full_name="Research Student")
    subject = seed.subject(db_session, "Co so du lieu")
    classroom = seed.classroom(db_session, "DB-01", subject, teacher)
    seed.enroll(db_session, student, classroom)
    document = seed.document(
        db_session,
        subject,
        classroom,
        teacher,
        filename="db-intro.pdf",
        title="Database Introduction",
        file_path="temp_uploads/db-intro.pdf",
    )
    seed.question(
        db_session,
        subject,
        content="He quan tri co so du lieu la gi?",
        options=["A. DBMS", "B. CPU", "C. RAM", "D. API"],
        correct_answer="A",
        source_file=document.filename,
        explanation="DBMS la he thong quan tri co so du lieu va quan ly truy xuat du lieu.",
    )
    seed.document_eval(db_session, student, document, score=42.0, attempts=2, completed=False)
    db_session.add(
        models.StudentDocumentScoreHistory(
            user_id=student.id,
            document_id=document.id,
            subject_id=subject.id,
            class_id=classroom.id,
            score=42.0,
            test_type="chapter",
            total_questions=10,
            correct_count=4,
        )
    )
    db_session.add(
        models.AssessmentHistory(
            user_id=student.id,
            subject_id=subject.id,
            subject=subject.name,
            score=42.0,
            total_questions=10,
            correct_count=4,
            test_type="chapter",
            level_at_time="Beginner",
        )
    )
    db_session.commit()
    return teacher, student, subject, classroom, document


def test_research_bootstrap_and_run_orbit_suite(client_factory, db_session, seed):
    _seed_research_data(db_session, seed)
    client = client_factory((research.router, "/api/research"))

    bootstrap_response = client.post("/api/research/agents/bootstrap")
    assert bootstrap_response.status_code == 200
    payload = bootstrap_response.json()
    assert payload["ok"] is True
    assert any(item["key"] == "orbit_agent" for item in payload["agents"])
    assert any(item["agent_key"] == "orbit_agent" for item in payload["cases"])

    run_response = client.post("/api/research/agents/orbit_agent/run-suite")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["component"] == "multi_agent"
    assert run_payload["metrics"]["task_success_rate"] >= 1.0
    assert run_payload["results"]

    history_response = client.get("/api/research/history")
    assert history_response.status_code == 200
    history_items = history_response.json()["items"]
    assert any(item["component"] == "multi_agent" for item in history_items)


def test_research_rag_suite_and_report_generation(client_factory, db_session, seed, monkeypatch):
    _seed_research_data(db_session, seed)
    client = client_factory((research.router, "/api/research"))

    monkeypatch.setattr(
        AdaptiveAgent,
        "chat_with_tutor",
        lambda self, **kwargs: "DBMS la he thong quan tri co so du lieu va quan ly truy xuat du lieu.",
    )

    bootstrap_response = client.post("/api/research/rag/bootstrap")
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["cases"]

    run_response = client.post("/api/research/rag/run-suite")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["component"] == "rag"
    assert run_payload["metrics"]["faithfulness"] >= 0.0

    report_response = client.post("/api/research/reports/generate", json={"title": "Chapter 5 Demo"})
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert "## 5.2" in report_payload["markdown"]
    assert report_payload["download_url"].endswith(f"/api/research/reports/{report_payload['id']}/download")
    assert "rq2" in {key.lower(): value for key, value in report_payload["summary"].items()}

    download_response = client.get(f"/api/research/reports/{report_payload['id']}/download")
    assert download_response.status_code == 200
    assert download_response.headers["content-disposition"].endswith(".md")
    assert "# Chapter 5 Demo" in download_response.text


def test_research_case_export_downloads_csv(client_factory, db_session, seed, monkeypatch):
    _seed_research_data(db_session, seed)
    client = client_factory((research.router, "/api/research"))

    monkeypatch.setattr(
        AdaptiveAgent,
        "chat_with_tutor",
        lambda self, **kwargs: "DBMS la he thong quan tri co so du lieu va quan ly truy xuat du lieu.",
    )

    bootstrap_response = client.post("/api/research/agents/bootstrap")
    assert bootstrap_response.status_code == 200

    export_response = client.get("/api/research/export/cases?component=multi_agent")
    assert export_response.status_code == 200
    assert export_response.headers["content-disposition"].endswith(".csv")
    assert "component,agent_key" in export_response.text


def test_research_ocr_run_creates_history(client_factory, db_session, seed, monkeypatch):
    teacher, _, subject, classroom, _ = _seed_research_data(db_session, seed)
    client = client_factory((research.router, "/api/research"))

    def fake_grade_submission(self, *, batch_id, submissions, answer_key_bytes=None):
        return {
            "run_id": 99,
            "batch": {
                "id": batch_id,
            },
            "results": [
                {
                    "page_number": 1,
                    "original_image_url": "/temp_uploads/test_ocr/original.png",
                    "source_image_url": "/temp_uploads/test_ocr/processed.png",
                    "detected_student_id": "20222222",
                    "detected_exam_code": "001",
                    "detected_answers": ["A", "B", "C"],
                }
            ],
        }

    monkeypatch.setattr(OCRServiceUnderTest, "grade_submission", fake_grade_submission)

    png_bytes = io.BytesIO(b"fake-png").getvalue()
    response = client.post(
        "/api/research/ocr/run",
        data={
            "class_id": str(classroom.id),
            "teacher_id": str(teacher.id),
            "num_questions": "3",
            "ground_truth_json": '[{"page_number":1,"student_id":"20222222","exam_code":"001","answers":["A","B","C"]}]',
        },
        files={"image_files": ("sheet.png", png_bytes, "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["component"] == "ocr_omr"
    assert payload["metrics"]["accuracy"] >= 0.0

    history_response = client.get("/api/research/history?component=ocr_omr")
    assert history_response.status_code == 200
    assert len(history_response.json()["items"]) == 1
