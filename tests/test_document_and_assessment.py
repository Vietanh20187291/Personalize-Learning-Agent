from api import assessment as assessment_api
from api import document as document_api
from agents.assessment_agent import AssessmentAgent
from db import models


def test_append_question_bank_and_manual_crud(client_factory, db_session, seed, monkeypatch):
    teacher = seed.user(db_session, "doc.teacher@example.com", role="teacher", full_name="Doc Teacher")
    subject = seed.subject(db_session, "Data Structures")
    classroom = seed.classroom(db_session, "DS-1", subject, teacher, class_code="CLS-DS01")
    document = seed.document(
        db_session,
        subject,
        classroom,
        teacher,
        filename="ds.pdf",
        title="Data Structures Notes",
        visible=True,
    )

    def fake_pre_generate(self, subject, source_file, count=10, **kwargs):
        created = []
        subject_obj = self.db.query(models.Subject).filter_by(name=subject).first()
        existing = self.db.query(models.QuestionBank).filter_by(source_file=source_file).count()
        for idx in range(count):
            row = models.QuestionBank(
                subject_id=subject_obj.id,
                subject=subject,
                difficulty="Basic",
                content=f"Generated question {existing + idx + 1}",
                options=["A. One", "B. Two", "C. Three", "D. Four"],
                correct_answer="A",
                explanation="Generated fallback",
                source_file=source_file,
            )
            self.db.add(row)
            self.db.flush()
            created.append(
                {
                    "id": row.id,
                    "content": row.content,
                    "options": row.options,
                    "correct_answer": row.correct_answer,
                    "explanation": row.explanation,
                }
            )
        self.db.commit()
        return created

    monkeypatch.setattr(document_api.AssessmentAgent, "pre_generate_questions_for_document", fake_pre_generate)

    client = client_factory((document_api.router, "/api/documents"))

    first_append = client.post(f"/api/documents/generate-question-bank/{document.id}/append?count=10")
    assert first_append.status_code == 200
    assert first_append.json()["generated_count"] == 10
    assert first_append.json()["final_count"] == 10

    second_append = client.post(f"/api/documents/generate-question-bank/{document.id}/append?count=10")
    assert second_append.status_code == 200
    assert second_append.json()["generated_count"] == 10
    assert second_append.json()["final_count"] == 20

    create_manual = client.post(
        f"/api/documents/question-bank/{document.id}",
        json={
            "content": "Manual question",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "B",
            "explanation": "Manual explanation",
            "difficulty": "Hard",
        },
    )
    assert create_manual.status_code == 200
    question_id = create_manual.json()["id"]

    update_manual = client.put(
        f"/api/documents/question-bank/{question_id}",
        json={"content": "Manual question updated", "difficulty": "Medium"},
    )
    assert update_manual.status_code == 200
    assert update_manual.json()["content"] == "Manual question updated"

    delete_manual = client.delete(f"/api/documents/question-bank/{question_id}")
    assert delete_manual.status_code == 200
    assert db_session.query(models.QuestionBank).filter_by(id=question_id).first() is None


def test_assessment_generate_session_and_submit_persists_scores(
    client_factory,
    db_session,
    seed,
    monkeypatch,
):
    student = seed.user(db_session, "assess.student@example.com", role="student", full_name="Assess Student")
    teacher = seed.user(db_session, "assess.teacher@example.com", role="teacher", full_name="Assess Teacher")
    subject = seed.subject(db_session, "Algorithms")
    classroom = seed.classroom(db_session, "ALGO-1", subject, teacher, class_code="CLS-ALGO1")
    seed.enroll(db_session, student, classroom)
    document = seed.document(
        db_session,
        subject,
        classroom,
        teacher,
        filename="algo.pdf",
        title="Algorithms Chapter 1",
        visible=True,
    )

    def fake_session_quiz(self, subject, session_topic, level, allowed_filenames=None):
        return [
            {
                "content": f"Session question {idx + 1}",
                "options": ["A. Correct", "B. Wrong 1", "C. Wrong 2", "D. Wrong 3"],
                "correct_label": "A",
                "explanation": "Because A is correct",
            }
            for idx in range(5)
        ]

    monkeypatch.setattr(assessment_api.AdaptiveAgent, "generate_session_quiz", fake_session_quiz)
    monkeypatch.setattr(assessment_api, "_run_post_submit_updates", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        assessment_api,
        "compute_subject_score_metrics",
        lambda **kwargs: {"test_score": 80.0, "progress_score": 40.0},
    )

    client = client_factory((assessment_api.router, "/api/assessment"))

    generate_resp = client.post(
        "/api/assessment/generate-session",
        json={
            "subject": subject.name,
            "user_id": student.id,
            "session_topic": "Sorting",
            "level": "Intermediate",
            "source_file": document.filename,
        },
    )
    assert generate_resp.status_code == 200
    generated_questions = generate_resp.json()["questions"]
    assert len(generated_questions) == 5
    assert db_session.query(models.QuestionBank).filter_by(subject=subject.name).count() == 5

    answers = []
    for index, item in enumerate(generated_questions):
        answers.append(
            {
                "question_id": item["id"],
                "selected_option": "A" if index < 4 else "B",
            }
        )

    submit_resp = client.post(
        "/api/assessment/submit",
        json={
            "subject": subject.name,
            "user_id": student.id,
            "answers": answers,
            "duration_seconds": 120,
            "is_session_quiz": True,
            "session_topic": "Sorting",
            "session_number": 1,
            "source_file": document.filename,
        },
    )
    assert submit_resp.status_code == 200
    submit_payload = submit_resp.json()
    assert submit_payload["is_passed"] is True
    assert submit_payload["correct_count"] == 4

    doc_eval = db_session.query(models.StudentDocumentEvaluation).filter_by(
        user_id=student.id,
        document_id=document.id,
    ).first()
    assert doc_eval is not None
    assert doc_eval.attempts == 1
    assert doc_eval.is_completed is True

    assert db_session.query(models.StudentDocumentScoreHistory).filter_by(user_id=student.id).count() == 1
    assert db_session.query(models.AssessmentHistory).filter_by(user_id=student.id).count() == 1


def test_assessment_agent_falls_back_when_llm_generation_returns_empty(db_session, seed, monkeypatch):
    teacher = seed.user(db_session, "fallback.teacher@example.com", role="teacher", full_name="Fallback Teacher")
    subject = seed.subject(db_session, "Computer Architecture")
    classroom = seed.classroom(db_session, "CA-1", subject, teacher, class_code="CLS-CA01")
    seed.document(
        db_session,
        subject,
        classroom,
        teacher,
        filename="arch.pdf",
        title="Architecture Notes",
        visible=True,
    )

    agent = AssessmentAgent(db_session)

    monkeypatch.setattr(agent, "_build_rag_context", lambda subject, allowed_files=None: "")
    monkeypatch.setattr(
        agent,
        "_fallback_concepts_for_subject",
        lambda subject, limit=20: [f"concept {idx}" for idx in range(limit)],
    )
    monkeypatch.setattr(agent, "_generate_batch_questions_with_llm", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        agent,
        "generate_questions_from_concepts",
        lambda concepts, count: [
            {
                "question": f"Fallback question {idx + 1}",
                "options": ["A. One", "B. Two", "C. Three", "D. Four"],
                "correct_answer": "A",
                "bloom_level": "understand",
                "explanation": "Local fallback",
            }
            for idx in range(count)
        ],
    )

    saved = agent.pre_generate_questions_for_document(
        subject=subject.name,
        source_file="arch.pdf",
        count=5,
        force_refresh=True,
        replace_existing=True,
    )
    assert len(saved) == 5
    assert db_session.query(models.QuestionBank).filter_by(subject=subject.name, source_file="arch.pdf").count() == 5
