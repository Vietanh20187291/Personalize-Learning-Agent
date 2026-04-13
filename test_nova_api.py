import json
import urllib.request

url = 'http://127.0.0.1:8000/api/teacher/nova-interactive'
data = {
    'teacher_id': 2,
    'class_id': 1,
    'message': 'tóm tắt lớp IT1'
}

req = urllib.request.Request(
    url,
    data=json.dumps(data).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode('utf-8'))
        print("✅ SUCCESS")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
except urllib.error.HTTPError as e:
    body = e.read().decode('utf-8')
    print(f"❌ ERROR {e.code}: {body[:200]}")
except Exception as e:
    print(f"❌ ERROR: {e}")
