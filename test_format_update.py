#!/usr/bin/env python
import requests
import json

print("╔═══════════════════════════════════════════════════════════╗")
print("║ TEST NOVA - Class Summary Format Update                  ║")
print("╚═══════════════════════════════════════════════════════════╝\n")

# Test 1: Tóm tắt lớp IT2
print("TEST 1: Tóm tắt tình hình lớp IT2\n")
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
    print("📋 RESPONSE:\n")
    print(result.get('reply', 'No reply'))
    print("\n" + "="*60 + "\n")
except Exception as e:
    print(f"Error: {e}\n")

# Test 2: Tóm tắt lớp IT1
print("TEST 2: Tóm tắt lớp IT1 (phân tích chi tiết)\n")
try:
    response = requests.post(
        'http://127.0.0.1:8000/api/teacher/nova-interactive',
        json={
            'teacher_id': 1,
            'class_id': 1,  # IT1
            'message': 'Phân tích lớp IT1'
        },
        timeout=10
    )
    
    print(f"Status: {response.status_code}\n")
    result = response.json()
    print("📋 RESPONSE:\n")
    print(result.get('reply', 'No reply'))
except Exception as e:
    print(f"Error: {e}")
