import sys
sys.path.insert(0, 'backend')

from db.database import SessionLocal
from agents.teacher_agent import TeacherAgent

db = SessionLocal()
try:
    agent = TeacherAgent(db)
    result = agent.respond(
        teacher_id=1,
        class_id=2,
        message="Tóm tắt tình hình lớp IT2"
    )
    print("Respond() result reply:")
    print("=" * 60)
    print(result['reply'])
    print("=" * 60)
finally:
    db.close()
