import sys
sys.path.insert(0, '.')

from db.database import SessionLocal
from agents.teacher_agent import TeacherAgent
from db.models import Classroom

db = SessionLocal()
try:
    agent = TeacherAgent(db)
    classroom = db.query(Classroom).filter(Classroom.id == 2).first()
    if classroom:
        result = agent._class_overview_reply(classroom, None, {})
        print("Result reply:")
        print("=" * 60)
        print(result['reply'])
        print("=" * 60)
        print("\nFirst 100 chars:")
        print(result['reply'][:100])
    else:
        print("Classroom not found")
finally:
    db.close()
