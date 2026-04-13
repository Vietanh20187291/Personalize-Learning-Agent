import sqlite3
import json
import requests

# Get valid teacher and class
conn = sqlite3.connect('test.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT c.id, c.teacher_id, c.name 
    FROM classrooms c 
    WHERE c.teacher_id IS NOT NULL 
    LIMIT 1
""")
result = cursor.fetchone()
class_id, teacher_id, class_name = result
conn.close()

messages = [
    "tóm tắt tình hình lớp",           # Original message
    "tình hình lớp IT1 như thế nào",    # Different phrasing
    "lớp",                              # Simple query
    "học sinh",                         # Student focus
    "thống kê lớp",                     # Stats focus
]

url = "http://localhost:8000/api/teacher/nova-interactive"
client_timeout = 40  # Longer timeout to match server

for msg in messages:
    print(f"\n{'='*80}")
    print(f"Message: '{msg}'")
    print('='*80)
    
    payload = {
        "teacher_id": teacher_id,
        "class_id": class_id,
        "message": msg
    }
    
    try:
        response = requests.post(url, json=payload, timeout=client_timeout)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Status: 200")
            print(f"Intent: {data.get('intent_type')}")
            print(f"Confidence: {data.get('confidence'):.2f}")
            print(f"Target: {data['action_metadata'].get('target')} → {data['action_metadata'].get('tab_name')}")
            print(f"Reply (first 100 chars): {data['reply'][:100]}...")
        else:
            print(f"✗ Status: {response.status_code}")
            try:
                print(f"Error: {response.json()}")
            except:
                print(f"Error: {response.text[:200]}")
                
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
