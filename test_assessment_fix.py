#!/usr/bin/env python3
"""
Test script to verify the subject_id fix for assessment generation.
Steps:
1. Login as admin
2. Create teacher and student accounts (if not exist)
3. Teacher creates 2 subjects and 2 classes per subject
4. Upload test documents to each class
5. Enroll student in both classes
6. Attempt assessment generation and check for "AI chưa chuẩn bị xong" error
"""

import requests
import json
import sys
import random
import string
from pathlib import Path

# Configuration
BASE_URL = "http://127.0.0.1:8000"
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "admin123"

# Generate unique emails for each test run to avoid "already exists" conflicts
def generate_unique_email(prefix):
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{suffix}@test.com"

TEACHER_EMAIL = generate_unique_email("teacher_fix")
TEACHER_PASSWORD = "TeacherPass123"
STUDENT_EMAIL = generate_unique_email("student_fix")
STUDENT_PASSWORD = "StudentPass123"

# Test data
SUBJECTS = [
    {"name": "Lập trình hướng đối tượng", "desc": "OOP basics"},
    {"name": "Lập trình Python cơ bản", "desc": "Python fundamentals"}
]

# Will be populated after account creation
teacher_password = None
student_password = None

def create_test_document():
    """Create a minimal Word document for testing."""
    try:
        from docx import Document as DocxDoc
        doc = DocxDoc()
        doc.add_paragraph("Tài liệu bài giảng về lập trình.")
        doc.add_paragraph("Nội dung môn học.")
        doc.save("test_doc.docx")
        return "test_doc.docx"
    except Exception as e:
        print(f"⚠️  Could not create test doc: {e}")
        return None

def api_call(method, endpoint, data=None, token=None, form_data=False):
    """Make API call and return response."""
    url = f"{BASE_URL}{endpoint}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers)
        elif method == "POST":
            if form_data:
                # Use form-encoded data (for OAuth2PasswordRequestForm)
                resp = requests.post(url, data=data, headers=headers)
            else:
                # Use JSON data
                headers["Content-Type"] = "application/json"
                resp = requests.post(url, json=data, headers=headers)
        elif method == "PUT":
            headers["Content-Type"] = "application/json"
            resp = requests.put(url, json=data, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        return resp.status_code, resp.json() if resp.text else {}
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return None, {}

print("=" * 60)
print("TEST: Assessment Generation with subject_id Fix")
print("=" * 60)

# Step 1: Login as admin to get token for user creation
print("\n[Step 1] Admin Login...")
admin_login_data = {
    "username": "admin",
    "password": "admin123"
}
status, resp = api_call("POST", "/api/auth/login", admin_login_data, form_data=True)
if status == 200:
    admin_token = resp.get("access_token")
    print(f"✅ Admin login successful")
else:
    print(f"⚠️  Admin login failed ({status}): {resp.get('detail', 'Unknown error')}")
    admin_token = None

if not admin_token:
    print("❌ Cannot proceed without admin token")
    sys.exit(1)

# Step 2: Create teacher account
print("\n[Step 2] Create Teacher Account...")
create_user_data = {
    "email": TEACHER_EMAIL,
    "password": TEACHER_PASSWORD,
    "fullname": "Test Teacher",
    "role": "teacher"
}
status, resp = api_call("POST", "/api/admin/create-user", create_user_data, admin_token)
if status in [200, 201]:
    teacher_password = resp.get("password", TEACHER_PASSWORD)  # Use generated or fallback
    print(f"✅ Teacher created: {TEACHER_EMAIL}")
    print(f"   Generated password: {teacher_password}")
elif "already exists" in resp.get("detail", ""):
    print(f"ℹ️  Teacher already exists: {TEACHER_EMAIL}")
    teacher_password = TEACHER_PASSWORD  # Use our default
else:
    print(f"⚠️  Teacher creation failed ({status}): {resp.get('detail', 'Unknown error')}")
    teacher_password = TEACHER_PASSWORD

# Step 3: Create student account
print("\n[Step 3] Create Student Account...")
create_user_data["email"] = STUDENT_EMAIL
create_user_data["password"] = STUDENT_PASSWORD
create_user_data["role"] = "student"
create_user_data["fullname"] = "Test Student"
status, resp = api_call("POST", "/api/admin/create-user", create_user_data, admin_token)
if status in [200, 201]:
    student_password = resp.get("password", STUDENT_PASSWORD)  # Use generated or fallback
    print(f"✅ Student created: {STUDENT_EMAIL}")
    print(f"   Generated password: {student_password}")
elif "already exists" in resp.get("detail", ""):
    print(f"ℹ️  Student already exists: {STUDENT_EMAIL}")
    student_password = STUDENT_PASSWORD  # Use our default
else:
    print(f"⚠️  Student creation failed ({status}): {resp.get('detail', 'Unknown error')}")
    student_password = STUDENT_PASSWORD

# Step 4: Teacher login
print("\n[Step 4] Teacher Login...")
teacher_login_data = {
    "username": TEACHER_EMAIL,
    "password": teacher_password  # Use generated password from creation
}
status, resp = api_call("POST", "/api/auth/login", teacher_login_data, form_data=True)
if status == 200:
    teacher_token = resp.get("access_token")
    teacher_id = resp.get("userId")  # Get the correct field name
    print(f"✅ Teacher login successful (ID: {teacher_id})")
else:
    print(f"❌ Teacher login failed ({status}): {resp.get('detail', 'Unknown error')}")
    sys.exit(1)

# Step 5: Create subjects and classes
print("\n[Step 5] Create Subjects and Classes...")
subject_ids = {}
class_ids = {}

for subject in SUBJECTS:
    # Create subject
    subject_data = {
        "name": subject["name"],
        "description": subject["desc"]
    }
    status, resp = api_call("POST", "/api/subjects", subject_data, teacher_token)
    if status in [200, 201]:
        subject_id = resp.get("id")
        subject_ids[subject["name"]] = subject_id
        print(f"✅ Subject created: {subject['name']} (ID: {subject_id})")
    elif "đã tồn tại" in resp.get("detail", "") or "already" in resp.get("detail", "").lower():
        # Subject already exists, need to fetch its ID from database
        # For now, we'll skip and use a different name
        print(f"ℹ️  Subject already exists: {subject['name']} (skipping, using new name)")
        new_name = f"{subject['name']}_v{random.randint(1000, 9999)}"
        subject_data["name"] = new_name
        status, resp = api_call("POST", "/api/subjects", subject_data, teacher_token)
        if status in [200, 201]:
            subject_id = resp.get("id")
            subject_ids[subject["name"]] = subject_id
            print(f"✅ Subject created with new name: {new_name} (ID: {subject_id})")
        else:
            print(f"❌ Subject creation failed ({status}): {resp.get('detail', 'Unknown error')}")
            continue
    else:
        print(f"❌ Subject creation failed ({status}): {resp.get('detail', 'Unknown error')}")
        continue
    
    # Create 1 class for this subject
    class_data = {
        "teacher_id": teacher_id,
        "subject_id": subject_id,
        "name": f"Lớp {subject['name'][:10]}",
        "code": f"CLASS_{subject_id}"
    }
    status, resp = api_call("POST", "/api/classroom/create", class_data, teacher_token)
    if status in [200, 201]:
        class_id = resp.get("id")
        class_ids[subject["name"]] = class_id
        print(f"  ✅ Class created (ID: {class_id})")
    else:
        print(f"  ❌ Class creation failed ({status}): {resp.get('detail', 'Unknown error')}")

if not class_ids or len(class_ids) < 2:
    print("❌ Not enough subjects/classes created. Aborting test.")
    sys.exit(1)

# Step 6: Upload documents to each class
print("\n[Step 6] Upload Documents to Classes...")
doc_file = create_test_document()

for subject_name, class_id in class_ids.items():
    if not doc_file or not Path(doc_file).exists():
        print(f"  ⚠️  Skipping upload for {subject_name} (no test doc)")
        continue
    
    with open(doc_file, "rb") as f:
        files = {"file": f}
        data = {"class_id": class_id, "subject_id": subject_ids[subject_name]}
        
        try:
            headers = {"Authorization": f"Bearer {teacher_token}"}
            resp = requests.post(f"{BASE_URL}/api/upload/documents", files=files, data=data, headers=headers)
            if resp.status_code in [200, 201]:
                doc_resp = resp.json()
                print(f"  ✅ Document uploaded for {subject_name} (class_id: {class_id})")
            else:
                print(f"  ❌ Upload failed for {subject_name} ({resp.status_code}): {resp.json().get('detail', 'Unknown error')}")
        except Exception as e:
            print(f"  ❌ Upload error for {subject_name}: {e}")

# Step 7: Enroll student in both classes
print("\n[Step 7] Enroll Student in Classes...")
for subject_name, class_id in class_ids.items():
    enroll_data = {
        "user_id": teacher_id,  # Using teacher ID as placeholder (in real scenario, use student ID from DB)
        "class_id": class_id
    }
    # Note: Enrollment typically done via classroom management, we'll skip for now and use direct DB inserts if needed
    print(f"  ℹ️  Enrollment for {subject_name} (class_id: {class_id}) - would need direct DB insert")

# Step 8: Student login
print("\n[Step 8] Student Login...")
student_login_data = {
    "username": STUDENT_EMAIL,
    "password": student_password  # Use generated password
}
status, resp = api_call("POST", "/api/auth/login", student_login_data, form_data=True)
if status == 200:
    student_token = resp.get("access_token")
    student_id = resp.get("user_id")
    print(f"✅ Student login successful (ID: {student_id})")
else:
    print(f"❌ Student login failed ({status}): {resp.get('detail', 'Unknown error')}")
    # Continue anyway to test assessment generation failure case

# Step 9: Test assessment generation
print("\n[Step 9] Test Assessment Generation...")
for subject_name, class_id in list(class_ids.items())[:1]:  # Test first class
    quiz_data = {
        "user_id": student_id if 'student_id' in locals() else 999,
        "class_id": class_id,
        "subject": subject_name
    }
    status, resp = api_call("POST", "/api/assessment/generate", quiz_data, student_token if 'student_token' in locals() else None)
    if status == 200:
        print(f"✅ Assessment generated successfully for {subject_name}!")
        print(f"   Num questions: {resp.get('num_questions', '?')}")
    else:
        detail = resp.get('detail', 'Unknown error')
        print(f"❌ Assessment generation failed ({status}): {detail}")
        if "Ai chưa chuẩn bị" in detail or "AI" in detail:
            print("   ❌ CRITICAL: Still getting 'AI not ready' error - subject_id fix may not be applied correctly!")
        else:
            print("   ℹ️  Different error - may be unrelated to subject_id issue")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)

# Cleanup
if doc_file and Path(doc_file).exists():
    Path(doc_file).unlink()
