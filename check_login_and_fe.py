import requests

print('BACKEND LOGIN')
try:
    r = requests.post('http://localhost:8000/api/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=20)
    print(r.status_code)
    print(r.headers.get('content-type'))
    print(r.text[:400])
except Exception as e:
    print(type(e).__name__, e)

print('\nFRONTEND PAGES')
for url in ['http://localhost:3000/auth', 'http://localhost:3001/auth']:
    try:
        r = requests.get(url, timeout=10)
        print(url, r.status_code, r.headers.get('content-type'))
    except Exception as e:
        print(url, type(e).__name__, e)
