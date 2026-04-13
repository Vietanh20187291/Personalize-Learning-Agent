import urllib.request
import json

# Test Ollama is working
try:
    req = urllib.request.Request('http://localhost:11434/api/tags', method='GET')
    with urllib.request.urlopen(req, timeout=3) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        models = data.get('models', [])
        print(f'✅ Ollama hoạt động! Có {len(models)} model:')
        for model in models:
            print(f'   - {model.get("name")}')
except Exception as e:
    print(f'❌ Ollama không hoạt động: {e}')
    print('   Hãy chạy: ollama serve')
