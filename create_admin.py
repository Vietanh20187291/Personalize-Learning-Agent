#!/usr/bin/env python3
import sys
sys.path.insert(0, r'c:\Users\DELL\Desktop\2023\LVTN\New\ai-personalized-learning-Test1\backend')

from db.database import SessionLocal, engine
from db import models
from db.models import User
from passlib.context import CryptContext

# Tạo tables
models.Base.metadata.create_all(bind=engine)

# Use argon2 instead of bcrypt
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

db = SessionLocal()
try:
    # Kiểm tra xem admin đã tồn tại hay chưa
    admin_exists = db.query(User).filter(User.username == "admin").first()
    
    if admin_exists:
        print(f"✅ Admin đã tồn tại: {admin_exists.username}")
    else:
        print("🚀 Tạo admin user...")
        # Hash password using argon2
        password = "admin123"
        hashed = pwd_context.hash(password)
        
        admin_user = User(
            username="admin",
            hashed_password=hashed,
            role="admin",
            full_name="Quản trị viên"
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print(f"✅ Admin created successfully!")
        print(f"   Username: admin")
        print(f"   Password: admin123")
        print(f"   Role: admin")
        
    # Liệt kê tất cả users
    print("\n📋 All users in database:")
    users = db.query(User).all()
    for user in users:
        print(f"  - {user.username} (Role: {user.role})")
        
except Exception as e:
    print(f"❌ Error: {e}")
    db.rollback()
finally:
    db.close()
