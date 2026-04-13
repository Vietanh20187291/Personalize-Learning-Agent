import json
import urllib.request

url = 'http://127.0.0.1:8000/api/classroom/teacher/2'
try:
    with urllib.request.urlopen(url) as resp:
        result = json.loads(resp.read().decode('utf-8'))
        print('✅ Success:', len(result), 'classes')
        for c in result:
            print(f"   - {c['id']}: {c['name']}")
except urllib.error.HTTPError as e:
    print(f'❌ HTTP {e.code}: {e.read().decode()}')
except Exception as e:
    print(f'❌ Error: {e}')
