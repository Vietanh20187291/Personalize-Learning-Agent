# Quick Start - LLM Debug Viewer

## 🎯 Open Debug Viewer Now

### Option 1: Direct File (Easiest)
```
file:///c:/Users/DELL/Desktop/2023/LVTN/New/ai-personalized-learning-Test1/backend/debug_viewer.html
```
Just copy-paste into browser address bar.

### Option 2: Via Simple HTTP Server
```powershell
cd c:\Users\DELL\Desktop\2023\LVTN\New\ai-personalized-learning-Test1\backend
python -m http.server 9000
```
Then visit: `http://localhost:9000/debug_viewer.html`

---

## 🧪 Test It Immediately

While debug viewer is open, run:
```powershell
# In PowerShell
$body = @{
    teacher_id = 2
    class_id = 1
    message = "Tình hình lớp IT1 thế nào?"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/teacher/respond" `
  -Method Post `
  -Headers @{"Content-Type"="application/json"} `
  -Body $body
```

**Watch debug viewer** - you'll see:
- ✅ REQUEST event (blue) with full prompt
- ✅ RESPONSE event (green) with LLM output and duration

---

## 📊 What You'll See

### Request Event
```
[14:30:00] ➜ Request
  System Prompt: Phân loại intent cho Teacher Agent...
  User Prompt: Tình hình lớp IT1 thế nào?...
```

### Response Event
```
[14:30:02] ⬅ Response (2334 ms)
  Response: {"intent_type": "class_overview", ...}
```

---

## ⚡ Performance Metrics

From the events you see:
- **Duration_ms** = Actual LLM call time
- **Real bottleneck visible** = Monitor multiple requests
- **Cache efficiency** = Notice if same message has NO events (cached!)

---

## 🔄 Multiple Requests

Try these in order (watch debug viewer):

```bash
# 1st request - NEW (will see events)
"Tình hình lớp IT1 thế nào?"

# 2nd request - SAME (NO events - cached!)
"Tình hình lớp IT1 thế nào?"

# 3rd request - DIFFERENT (will see events again)
"Lớp IT1 học thế nào?"

# 4th request - SAME as 3rd (NO events - cached!)
"Lớp IT1 học thế nào?"
```

---

## 💡 Key Observations

✅ **First request:** ➜ → ⬅ (LLM called, ~2000ms)  
✅ **Second identical:** NO events (cache hit!)  
✅ **Different message:** ➜ → ⬅ (new LLM call)  
✅ **Connection:** Green indicator = online  
✅ **Counters:** Increment on each event  

---

## 🐛 If No Events Appear

1. **Verify backend running:**
   ```powershell
   curl http://localhost:8000/docs
   ```
   Should get HTML response.

2. **Check browser console (F12):**
   - Click F12 → Console tab
   - Look for errors
   - Check Network tab → WS section (should see EventSource connection)

3. **Test SSE endpoint directly:**
   ```powershell
   curl http://localhost:8000/debug/stream
   ```
   Should keep connection open.

---

## 📁 Files Modified

✅ `/backend/debug_stream.py` - Event manager (NEW)  
✅ `/backend/api/debug.py` - SSE endpoint (NEW)  
✅ `/backend/debug_viewer.html` - UI (NEW)  
✅ `/backend/agents/teacher_agent.py` - Emit events  
✅ `/backend/main.py` - Register router  

---

## 🎨 Debug Viewer Features

- **Live Status Indicator:** Green = connected
- **Event Counters:** Tracks requests/responses
- **Auto-Scroll:** Newest logs at bottom
- **Full Content:** See complete prompts & responses
- **Timestamps:** Know exactly when events occurred
- **Dark Theme:** Easy on the eyes
- **Real-time Updates:** Sub-100ms latency

---

## 🚀 You're Ready!

1. ✅ Backend running on port 8000
2. ✅ Frontend running on port 3000
3. ✅ SSE streaming endpoint active
4. ✅ Debug viewer HTML ready to use
5. ✅ TeacherAgent emitting events

**Next:** Open debug viewer and make a request! 🎯

---

For full details, see: `DEBUG_VIEWER_GUIDE.md`
