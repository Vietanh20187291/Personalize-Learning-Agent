from api import orbit as orbit_api
from api import planning as planning_api
from api import teacher_agent as teacher_api
from db import models


def test_planning_regenerate_and_chat_adjustment_reorders_steps(
    client_factory,
    db_session,
    seed,
):
    student = seed.user(db_session, "plan.student@example.com", role="student", full_name="Plan Student")
    teacher = seed.user(db_session, "plan.teacher@example.com", role="teacher", full_name="Plan Teacher")

    oop = seed.subject(db_session, "OOP")
    database = seed.subject(db_session, "Database")
    oop_class = seed.classroom(db_session, "OOP-1", oop, teacher, class_code="CLS-OOP1")
    db_class = seed.classroom(db_session, "DB-1", database, teacher, class_code="CLS-DB1")
    seed.enroll(db_session, student, oop_class)
    seed.enroll(db_session, student, db_class)

    oop_doc = seed.document(db_session, oop, oop_class, teacher, filename="oop.pdf", title="OOP Doc", visible=True)
    db_doc = seed.document(db_session, database, db_class, teacher, filename="db.pdf", title="DB Doc", visible=True)
    seed.document_eval(db_session, student, oop_doc, score=25.0, attempts=1, completed=False)
    assert db_doc.id != oop_doc.id

    client = client_factory((planning_api.router, "/api/planning"))

    regenerate_resp = client.post(
        "/api/planning/plan/regenerate",
        json={"user_id": student.id, "reason": "manual"},
    )
    assert regenerate_resp.status_code == 200
    plan = regenerate_resp.json()["plan"]
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["document_id"] == oop_doc.id
    assert plan["steps"][0]["priority_group"] == "low_score"

    adjust_resp = client.post(
        "/api/planning/chat",
        json={"user_id": student.id, "message": "Dua mon OOP hoc sau"},
    )
    assert adjust_resp.status_code == 200
    adjusted_plan = adjust_resp.json()["plan"]
    assert adjusted_plan["steps"][-1]["subject_name"] == "OOP"


def test_orbit_document_followup_uses_open_document_context_and_persists_history(
    client_factory,
    db_session,
    seed,
    monkeypatch,
):
    student = seed.user(db_session, "orbit.student@example.com", role="student", full_name="Orbit Student")
    teacher = seed.user(db_session, "orbit.teacher@example.com", role="teacher", full_name="Orbit Teacher")
    subject = seed.subject(db_session, "Operating Systems")
    classroom = seed.classroom(db_session, "OS-1", subject, teacher, class_code="CLS-OS01")
    seed.enroll(db_session, student, classroom)
    document = seed.document(
        db_session,
        subject,
        classroom,
        teacher,
        filename="os-intro.pdf",
        title="OS Intro",
        visible=True,
    )
    seed.chunk(db_session, subject, document.filename, "Operating systems manage processes, threads, memory and I/O.", classroom)

    def fake_chat_with_tutor(self, *args, **kwargs):
        return "Tom tat tai lieu da mo"

    monkeypatch.setattr(orbit_api.AdaptiveAgent, "chat_with_tutor", fake_chat_with_tutor)

    client = client_factory((orbit_api.router, "/api/orbit"))
    resp = client.post(
        "/api/orbit/chat",
        json={
            "user_id": student.id,
            "subject": subject.name,
            "class_id": classroom.id,
            "document_id": document.id,
            "message": "Tom tat tai lieu nay",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["reply"] == "Tom tat tai lieu da mo"
    assert payload["session_id"] is not None
    assert db_session.query(models.OrbitChatMessage).filter_by(user_id=student.id).count() == 2
    assert db_session.query(models.OrbitChatSession).filter_by(user_id=student.id).count() == 1


def test_orbit_open_document_request_returns_recommendation_and_teacher_directive(
    client_factory,
    db_session,
    seed,
):
    student = seed.user(db_session, "orbit2.student@example.com", role="student", full_name="Orbit Student 2")
    teacher = seed.user(db_session, "orbit2.teacher@example.com", role="teacher", full_name="Orbit Teacher 2")
    subject = seed.subject(db_session, "Networks")
    classroom = seed.classroom(db_session, "NET-1", subject, teacher, class_code="CLS-NET01")
    seed.enroll(db_session, student, classroom)
    document = seed.document(
        db_session,
        subject,
        classroom,
        teacher,
        filename="net.pdf",
        title="Network Basics",
        visible=True,
    )
    seed.document_eval(db_session, student, document, score=35.0, attempts=1, completed=False)

    client = client_factory((orbit_api.router, "/api/orbit"))

    recommend_resp = client.post(
        "/api/orbit/chat",
        json={
            "user_id": student.id,
            "subject": subject.name,
            "class_id": classroom.id,
            "message": "Mo tai lieu mon Networks cho toi",
        },
    )
    assert recommend_resp.status_code == 200
    recommend_payload = recommend_resp.json()
    assert recommend_payload["action_metadata"]["action_type"] == "open_document"
    assert recommend_payload["recommendation"]["document"]["id"] == document.id

    directive_resp = client.post(
        "/api/orbit/teacher-directive",
        json={
            "teacher_id": teacher.id,
            "student_id": student.id,
            "class_id": classroom.id,
            "subject": subject.name,
            "target_tests": 2,
            "target_chapters": 1,
            "note": "On lai chuong 1",
        },
    )
    assert directive_resp.status_code == 200
    assert db_session.query(models.OrbitCoachDirective).count() == 1


def test_nova_exam_flow_keeps_pending_request_and_routes_to_exam_tab(
    client_factory,
    db_session,
    seed,
    monkeypatch,
):
    teacher = seed.user(db_session, "nova.teacher@example.com", role="teacher", full_name="Nova Teacher")
    subject = seed.subject(db_session, "OOP")
    classroom = seed.classroom(db_session, "OOP-NOVA", subject, teacher, class_code="CLS-NOVA")

    def fake_generate_exam(self, subject, exam_type, num_questions, num_versions, difficulty=None):
        return {
            "reply": "Da chuan bi de thi thu.",
            "suggested_actions": ["Mo tab xuat de"],
            "generated_exam": {
                "subject": subject.name,
                "exam_type": exam_type,
                "num_questions": num_questions,
                "num_versions": num_versions,
            },
        }

    monkeypatch.setattr(teacher_api.TeacherAgent, "_generate_exam_versions", fake_generate_exam)

    client = client_factory((teacher_api.router, "/api/teacher"))

    first_resp = client.post(
        "/api/teacher/nova-interactive",
        json={
            "teacher_id": teacher.id,
            "class_id": classroom.id,
            "message": "Xuat de",
        },
    )
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    assert first_payload["needs_more_info"] is True
    assert "subject_name" in first_payload["missing_fields"]

    second_resp = client.post(
        "/api/teacher/nova-interactive",
        json={
            "teacher_id": teacher.id,
            "class_id": classroom.id,
            "message": "Trac nghiem mon OOP 20 cau 2 ma de",
        },
    )
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    assert second_payload["intent_type"] == "exam_generation"
    assert second_payload["action_metadata"]["tab_name"] == "exam"
