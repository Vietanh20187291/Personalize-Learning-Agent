from api import admin as admin_api
from api import auth as auth_api
from api import classroom as classroom_api
from api import subject as subject_api
from db import models


def test_register_and_login_creates_login_session_and_plan_refresh(
    client_factory,
    db_session,
    monkeypatch,
):
    calls = []

    def fake_regenerate(self, user_id, reason="manual", reference_login_at=None):
        calls.append({"user_id": user_id, "reason": reason})
        return {"id": 1}

    monkeypatch.setattr(auth_api.PlanningAgent, "regenerate_for_user", fake_regenerate)

    client = client_factory((auth_api.router, "/api/auth"))

    register_resp = client.post(
        "/api/auth/register",
        json={
            "fullname": "Student One",
            "email": "student1@example.com",
            "password": "secret123",
            "role": "student",
            "student_id": "SV001",
        },
    )
    assert register_resp.status_code == 200

    login_resp = client.post(
        "/api/auth/login",
        data={"username": "student1@example.com", "password": "secret123"},
    )
    assert login_resp.status_code == 200
    payload = login_resp.json()
    assert payload["role"] == "student"
    assert payload["studentId"] == "SV001"

    user = db_session.query(models.User).filter_by(username="student1@example.com").first()
    assert user is not None
    assert db_session.query(models.UserLoginSession).filter_by(user_id=user.id).count() == 1

    progress = db_session.query(models.StudentLearningProgress).filter_by(user_id=user.id).first()
    assert progress is not None
    assert progress.last_login_at is not None
    assert calls == [{"user_id": user.id, "reason": "login"}]


def test_admin_create_user_and_list_users(client_factory, db_session, seed):
    admin = seed.user(db_session, "admin@example.com", role="admin", full_name="Admin User")
    client = client_factory(
        (admin_api.router, "/api/admin"),
        overrides={admin_api.get_current_admin: lambda: admin},
    )

    create_resp = client.post(
        "/api/admin/create-user",
        json={
            "fullname": "Teacher Demo",
            "email": "teacher.demo@example.com",
            "role": "teacher",
        },
    )
    assert create_resp.status_code == 200
    create_payload = create_resp.json()
    assert create_payload["role"] == "teacher"
    assert create_payload["password"]

    list_resp = client.get("/api/admin/users")
    assert list_resp.status_code == 200
    users_payload = list_resp.json()
    assert users_payload["total"] == 1
    assert users_payload["users"][0]["email"] == "teacher.demo@example.com"


def test_subject_crud_and_classroom_join_rejects_second_class_same_subject(
    client_factory,
    db_session,
    seed,
):
    teacher = seed.user(db_session, "teacher@example.com", role="teacher", full_name="Teacher User")
    student = seed.user(
        db_session,
        "student2@example.com",
        role="student",
        full_name="Student User",
        student_id="SV002",
    )

    subject_client = client_factory(
        (subject_api.router, "/api/subjects"),
        overrides={subject_api.get_current_teacher: lambda: teacher},
    )

    create_subject_resp = subject_client.post(
        "/api/subjects",
        json={"name": "Discrete Math", "description": "Core math"},
    )
    assert create_subject_resp.status_code == 200
    subject_id = create_subject_resp.json()["id"]

    update_subject_resp = subject_client.put(
        f"/api/subjects/{subject_id}",
        json={"name": "Discrete Mathematics"},
    )
    assert update_subject_resp.status_code == 200
    assert update_subject_resp.json()["name"] == "Discrete Mathematics"

    subject = db_session.query(models.Subject).filter_by(id=subject_id).first()
    classroom_client = client_factory((classroom_api.router, "/api/classroom"))

    class_one_resp = classroom_client.post(
        "/api/classroom/create",
        json={"name": "DM-01", "subject_id": subject.id, "teacher_id": teacher.id},
    )
    assert class_one_resp.status_code == 200
    class_one_id = class_one_resp.json()["class_id"]
    class_one = db_session.query(models.Classroom).filter_by(id=class_one_id).first()

    class_two_resp = classroom_client.post(
        "/api/classroom/create",
        json={"name": "DM-02", "subject_id": subject.id, "teacher_id": teacher.id},
    )
    assert class_two_resp.status_code == 200
    class_two_code = class_two_resp.json()["class_code"]

    join_first_resp = classroom_client.post(
        "/api/classroom/join",
        json={"class_code": class_one.class_code, "user_id": student.id},
    )
    assert join_first_resp.status_code == 200

    join_second_resp = classroom_client.post(
        "/api/classroom/join",
        json={"class_code": class_two_code, "user_id": student.id},
    )
    assert join_second_resp.status_code == 400
    assert "Mỗi môn" in join_second_resp.json()["detail"]
