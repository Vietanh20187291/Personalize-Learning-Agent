#!/usr/bin/env python
import requests

print("╔═══════════════════════════════════════════════════════════╗")
print("║ TEST NOVA - Check if response is working                 ║")
print("╚═══════════════════════════════════════════════════════════╝\n")

# Test with exact same query to test_respond.py
print("TEST: Tóm tắt tình hình lớp IT2\n")
try:
    response = requests.post(
        'http://127.0.0.1:8000/api/teacher/nova-interactive',
        json={
            'teacher_id': 1,
            'class_id': 2,
            'message': 'Tóm tắt tình hình lớp IT2'
        },
        timeout=10
    )
    
    print(f"Status: {response.status_code}\n")
    result = response.json()
    print("Full reply:\n")
    print(result.get('reply', 'No reply'))
    
except Exception as e:
    print(f"Error: {e}")
