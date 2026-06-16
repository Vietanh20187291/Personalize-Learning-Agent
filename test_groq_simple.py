#!/usr/bin/env python3
"""Simple test to verify Groq API is working"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
project_root = Path(__file__).parent
load_dotenv(project_root / "backend" / ".env", override=True)

# Get API key
api_key = os.getenv("GROQ_KEY_ASSESSMENT")
if not api_key or api_key.startswith("dummy"):
    print("❌ GROQ_KEY_ASSESSMENT không được cấu hình hoặc là dummy key")
    sys.exit(1)

print(f"🔑 Using API Key: {api_key[:20]}...")

try:
    # Initialize Groq client
    client = Groq(api_key=api_key)
    print("✅ Groq client initialized successfully")
    
    # Test basic request
    print("\n📤 Sending test request to Groq...")
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "user", "content": "Xin chào, hãy trả lời 'Hello' bằng tiếng Việt"}
        ],
        max_tokens=100,
        temperature=0.7,
    )
    
    answer = response.choices[0].message.content
    print(f"✅ Groq phản hồi thành công!")
    print(f"📝 Câu trả lời: {answer}")
    print("\n✨ Groq đang hoạt động bình thường!")
    
except Exception as e:
    print(f"❌ Lỗi khi gọi Groq API:")
    print(f"   {type(e).__name__}: {str(e)}")
    sys.exit(1)
