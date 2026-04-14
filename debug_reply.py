#!/usr/bin/env python
import requests
import json

print("Checking raw JSON response...\n")

response = requests.post(
    'http://127.0.0.1:8000/api/teacher/nova-interactive',
    json={
        'teacher_id': 1,
        'class_id': 2,
        'message': 'Tóm tắt tình hình lớp IT2'
    },
    timeout=10
)

result = response.json()
reply = result.get('reply', '')

print(f"Reply length: {len(reply)}")
print(f"First 150 characters:")
print(repr(reply[:150]))
print(f"\nFormatted reply:")
print(reply[:200])
