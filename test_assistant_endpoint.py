#!/usr/bin/env python
import requests

# Test endpoint /api/teacher/assistant (instead of /nova-interactive)
print("Testing /api/teacher/assistant endpoint...\n")

response = requests.post(
    'http://127.0.0.1:8000/api/teacher/assistant',
    json={
        'teacher_id': 1,
        'class_id': 2,
        'message': 'Tóm tắt tình hình lớp IT2'
    },
    timeout=10
)

result = response.json()
reply = result.get('reply', '')

print(f"Status: {response.status_code}")
print(f"Reply length: {len(reply)}")
print(f"Reply preview:\n{reply[:200]}")
