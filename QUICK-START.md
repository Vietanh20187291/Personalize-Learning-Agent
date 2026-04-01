# 🚀 Quick Start Guide - AI Personalized Learning

## ⚡ Run Project (Simplest Way)

### Yêu cầu trước (Setup 1 lần duy nhất):
1. **Python 3.10+** cài sẵn và có trong PATH
2. **Node.js 18+** cài sẵn

### Lần đầu tiên (One-time setup):
```bash
# Terminal 1 - Backend Setup
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install fastapi uvicorn sqlalchemy python-dotenv pydantic requests
python main.py

# Terminal 2 - Frontend Setup
cd frontend
npm install
npm run dev
```

**Kết quả:**
- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs

---

## 📌 Lần Sau - Chỉ Cần Chạy 2 Lệnh

### Terminal 1 - Backend:
```bash
cd backend
.\venv\Scripts\activate
python main.py
```

### Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

---

## 🔑 Default Login Credentials

```
Username: admin
Password: admin123
```

---

## 🏗️ Project Architecture

```
Project Root
├── backend/                 (FastAPI server - Port 8000)
│   ├── main.py             (Entry point)
│   ├── venv/               (Python virtual environment)
│   ├── api/                (API routes)
│   ├── db/                 (Database models & SQLite)
│   └── agents/             (AI agents)
├── frontend/               (Next.js app - Port 3000)
│   ├── app/                (Pages)
│   ├── components/         (React components)
│   ├── services/           (API call services)
│   └── node_modules/       (npm packages)
```

---

## ❌ Troubleshooting

### Backend won't start - "Module not found" errors:
```bash
cd backend
.\venv\Scripts\activate
pip install --upgrade pip
pip install fastapi uvicorn sqlalchemy python-dotenv pydantic requests
python main.py
```

### Frontend won't start - npm packages missing:
```bash
cd frontend
npm install
npm run dev
```

### Port already in use:
```bash
# Change backend port:
cd backend
python main.py --port 8001

# Change frontend port:
cd frontend
npm run dev -- -p 3001
```

---

## 📋 Checklist Anh Em

- [ ] Python 3.10+ installed
- [ ] Node.js 18+ installed  
- [ ] Backend venv created & packages installed
- [ ] Frontend npm packages installed
- [ ] Backend running on port 8000
- [ ] Frontend running on port 3000
- [ ] Can login with admin/admin123
- [ ] Can access http://localhost:3000

✅ **Done!** Application is running and ready to use.
