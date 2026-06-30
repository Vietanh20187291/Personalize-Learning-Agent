"""
Agent Communication simulator (mockup) — A2A-style inter-agent coordination.

This module does NOT wire real agents together. It is a deterministic simulator
that visualizes how the Dual-Hub A2A Mesh architecture *would* coordinate the
sub-agents for a complex, multi-intent user request.

Architecture (3 layers):
  1. Agent Cards    — each sub-agent advertises its capabilities (A2A discovery).
  2. Task Planner   — the Hub (Nova / Orbit) decomposes the prompt into a DAG of
                      dependent tasks by pattern-matching against demo scenarios.
  3. Simulator      — walks the DAG and emits A2A lifecycle events
                      (submitted -> working -> completed) with the messages and
                      artifacts exchanged between agents.

Reference: Agent2Agent (A2A) Protocol — Google, 2025
           https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


# --------------------------------------------------------------------------- #
#  Layer 1 — Agent Cards (capability discovery contract)                       #
# --------------------------------------------------------------------------- #
# Each card is the public "contract" an agent exposes on the A2A mesh. The Hub
# reads these cards to decide which agent can serve which sub-task.
_AGENT_CARDS: Dict[str, Dict[str, Any]] = {
    "EvaluationAgent": {
        "name": "EvaluationAgent",
        "role": "analyzer",
        "family": "shared",
        "capabilities": ["score_student", "score_class", "find_weakest_subject", "find_weakest_document"],
        "input": {"student_id": "int?", "class_id": "int?", "document_id": "int?"},
        "artifact": "EvaluationReport",
        "description": "Đánh giá năng lực, tính điểm và tìm ra điểm yếu (môn/tài liệu).",
        "color": "#f59e0b",
    },
    "PlanningAgent": {
        "name": "PlanningAgent",
        "role": "planner",
        "family": "shared",
        "capabilities": ["make_improvement_plan", "schedule_study", "generate_roadmap"],
        "input": {"student_id": "int", "targets": "list", "horizon": "str?"},
        "artifact": "StudyPlan",
        "description": "Lập kế hoạch học tập / cải thiện theo mục tiêu và khung thời gian.",
        "color": "#3b82f6",
    },
    "AssessmentAgent": {
        "name": "AssessmentAgent",
        "role": "generator",
        "family": "shared",
        "capabilities": ["generate_quiz", "generate_exam_versions"],
        "input": {"subject": "str", "num_questions": "int", "num_versions": "int"},
        "artifact": "ExamPaper",
        "description": "Sinh đề trắc nghiệm / tự luận với nhiều mã đề.",
        "color": "#8b5cf6",
    },
    "TutorAgent": {
        "name": "TutorAgent",
        "role": "tutor",
        "family": "shared",
        "capabilities": ["adaptive_lesson", "explain_weak_topic"],
        "input": {"student_id": "int", "topic": "str", "level": "str?"},
        "artifact": "AdaptiveLesson",
        "description": "Gia sư thích ứng, đưa bài giảng theo trình độ và điểm yếu.",
        "color": "#10b981",
    },
    "ContentAgent": {
        "name": "ContentAgent",
        "role": "reader",
        "family": "shared",
        "capabilities": ["summarize_document", "extract_key_points"],
        "input": {"document_id": "int"},
        "artifact": "DocumentSummary",
        "description": "Đọc/tóm tắt tài liệu, rút ý chính làm ngữ cảnh cho các agent khác.",
        "color": "#ec4899",
    },
}

HUBS = {
    "nova": {
        "name": "Nova Hub",
        "role": "orchestrator",
        "audience": "teacher",
        "description": "Điều phối các sub-agent phục vụ giảng viên.",
        "color": "#ef4444",
    },
    "orbit": {
        "name": "Orbit Hub",
        "role": "orchestrator",
        "audience": "student",
        "description": "Điều phối các sub-agent phục vụ sinh viên.",
        "color": "#0ea5e9",
    },
}


# --------------------------------------------------------------------------- #
#  Layer 2 — Task Planner: prompt -> DAG of dependent tasks                    #
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _has_any(text: str, keywords: List[str]) -> bool:
    n = _norm(text)
    return any(k in n for k in keywords)


# A scenario = a recognizer + a DAG builder. Each step in the DAG carries the
# message the Hub sends and the artifact the receiving agent returns, which then
# becomes input for the next step (this is the inter-agent "communication").
def _build_eval_then_plan(prompt: str, hub: str) -> List[Dict[str, Any]]:
    student = _extract_token(prompt, [r"sinh viên\s+([A-Za-zÀ-ỹ0-9_ ]{1,30})", r"học sinh\s+([A-Za-zÀ-ỹ0-9_ ]{1,30})"]) or "A"
    student = student.strip().split()[0]
    return [
        {
            "step": 1,
            "from_agent": f"{hub} Hub",
            "to_agent": "EvaluationAgent",
            "task_id": "T1",
            "intent": "score_student + find_weakest_subject",
            "message": f"Yêu cầu đánh giá toàn diện sinh viên {student}, chỉ ra các môn điểm thấp nhất.",
            "artifact": {
                "name": "EvaluationReport",
                "payload": {"student": student, "weakest_subjects": ["Cơ sở dữ liệu", "Hệ điều hành"]},
            },
        },
        {
            "step": 2,
            "from_agent": "EvaluationAgent",
            "to_agent": "PlanningAgent",
            "task_id": "T2",
            "intent": "make_improvement_plan",
            "message": "Truyền EvaluationReport.weakest_subjects làm mục tiêu lập kế hoạch cải thiện.",
            "depends_on": "T1",
            "artifact": {
                "name": "StudyPlan",
                "payload": {"student": student, "focus_subjects": ["Cơ sở dữ liệu", "Hệ điều hành"], "weeks": 3},
            },
        },
    ]


def _build_eval_then_exam(prompt: str, hub: str) -> List[Dict[str, Any]]:
    subject = _extract_token(prompt, [r"môn\s+([A-Za-zÀ-ỹ0-9_ ]{1,30})"]) or "toán"
    subject = subject.strip().split()[0] if subject.strip() else "toán"
    num_q = _extract_number(prompt, [r"(\d+)\s*câu", r"(\d+)\s*question"]) or 20
    num_v = _extract_number(prompt, [r"(\d+)\s*mã đề", r"(\d+)\s*version"]) or 2
    return [
        {
            "step": 1,
            "from_agent": f"{hub} Hub",
            "to_agent": "EvaluationAgent",
            "task_id": "T1",
            "intent": "find_weakest_subject",
            "message": f"Tìm môn mà lớp có điểm trung bình thấp nhất để ưu tiên ra đề.",
            "artifact": {"name": "EvaluationReport", "payload": {"weakest_subject": subject}},
        },
        {
            "step": 2,
            "from_agent": "EvaluationAgent",
            "to_agent": "AssessmentAgent",
            "task_id": "T2",
            "intent": "generate_exam_versions",
            "message": f"Sinh đề trắc nghiệm môn {subject}: {num_q} câu, {num_v} mã đề.",
            "depends_on": "T1",
            "artifact": {"name": "ExamPaper", "payload": {"subject": subject, "num_questions": num_q, "num_versions": num_v}},
        },
    ]


def _build_eval_doc_then_plan(prompt: str, hub: str) -> List[Dict[str, Any]]:
    return [
        {
            "step": 1,
            "from_agent": f"{hub} Hub",
            "to_agent": "EvaluationAgent",
            "task_id": "T1",
            "intent": "find_weakest_document",
            "message": "Tìm tài liệu mà sinh viên có điểm kiểm tra kém nhất.",
            "artifact": {"name": "EvaluationReport", "payload": {"weakest_document": "chuong4_giaodien.docx", "latest_score": 42.5}},
        },
        {
            "step": 2,
            "from_agent": "EvaluationAgent",
            "to_agent": "PlanningAgent",
            "task_id": "T2",
            "intent": "schedule_study",
            "message": "Dựa vào tài liệu yếu nhất, lên lịch học trong tuần này.",
            "depends_on": "T1",
            "artifact": {"name": "StudyPlan", "payload": {"focus_document": "chuong4_giaodien.docx", "slots": 5, "horizon": "tuần này"}},
        },
    ]


def _build_content_eval_tutor(prompt: str, hub: str) -> List[Dict[str, Any]]:
    doc = _extract_token(prompt, [r"tài liệu\s+([A-Za-zÀ-ỹ0-9_.\- ]{1,40})"]) or "tài liệu X"
    doc = doc.strip().split()[0] if doc.strip() else "X"
    return [
        {
            "step": 1,
            "from_agent": f"{hub} Hub",
            "to_agent": "ContentAgent",
            "task_id": "T1",
            "intent": "summarize_document",
            "message": f"Đọc và tóm tắt tài liệu {doc}, rút ý chính.",
            "artifact": {"name": "DocumentSummary", "payload": {"document": doc, "key_points": 5}},
        },
        {
            "step": 2,
            "from_agent": "ContentAgent",
            "to_agent": "EvaluationAgent",
            "task_id": "T2",
            "intent": "score_student",
            "message": "Dùng DocumentSummary làm ngữ cảnh để chấm mức độ hiểu của sinh viên.",
            "depends_on": "T1",
            "artifact": {"name": "EvaluationReport", "payload": {"understanding_score": 61.0, "weak_topic": "Mô hình thực thể - kết hợp"}},
        },
        {
            "step": 3,
            "from_agent": "EvaluationAgent",
            "to_agent": "TutorAgent",
            "task_id": "T3",
            "intent": "adaptive_lesson",
            "message": "Đưa EvaluationReport.weak_topic cho Tutor để biên soạn bài giảng thích ứng.",
            "depends_on": "T2",
            "artifact": {"name": "AdaptiveLesson", "payload": {"topic": "Mô hình thực thể - kết hợp", "level": "Intermediate"}},
        },
    ]


def _build_eval_tutor_assessment(prompt: str, hub: str) -> List[Dict[str, Any]]:
    return [
        {
            "step": 1,
            "from_agent": f"{hub} Hub",
            "to_agent": "EvaluationAgent",
            "task_id": "T1",
            "intent": "find_weakest_subject",
            "message": "Xác định chương/môn yếu nhất cần ôn lại.",
            "artifact": {"name": "EvaluationReport", "payload": {"weak_topic": "Cấu trúc dữ liệu mảng"}},
        },
        {
            "step": 2,
            "from_agent": "EvaluationAgent",
            "to_agent": "TutorAgent",
            "task_id": "T2",
            "intent": "explain_weak_topic",
            "message": "Tutor giảng lại chủ đề yếu, kiểm tra mức độ nắm bắt.",
            "depends_on": "T1",
            "artifact": {"name": "AdaptiveLesson", "payload": {"topic": "Cấu trúc dữ liệu mảng", "understood": True}},
        },
        {
            "step": 3,
            "from_agent": "TutorAgent",
            "to_agent": "AssessmentAgent",
            "task_id": "T3",
            "intent": "generate_quiz",
            "message": "Sinh đề luyện tập củng cố chủ đề vừa ôn.",
            "depends_on": "T2",
            "artifact": {"name": "ExamPaper", "payload": {"topic": "Cấu trúc dữ liệu mảng", "num_questions": 10}},
        },
    ]


# Scenario registry: (recognizer predicate, scenario key, label, DAG builder)
_SCENARIOS: List[Dict[str, Any]] = [
    {
        "key": "eval_then_plan",
        "label": "Đánh giá sinh viên → Lập kế hoạch cải thiện",
        "recognize": lambda p, h: _has_any(p, ["rồi lập kế hoạch", "lập kế hoạch cải thiện", "kế hoạch cải thiện"]) and _has_any(p, ["đánh giá", "sinh viên", "học sinh"]),
        "build": _build_eval_then_plan,
    },
    {
        "key": "eval_then_exam",
        "label": "Tìm môn yếu → Tạo đề thi",
        "recognize": lambda p, h: _has_any(p, ["tạo đề", "ra đề", "mã đề", "trắc nghiệm"]) and _has_any(p, ["môn", "lớp", "điểm thấp", "yếu", "kém"]),
        "build": _build_eval_then_exam,
    },
    {
        "key": "eval_doc_then_plan",
        "label": "Tìm tài liệu yếu nhất → Lên lịch học",
        "recognize": lambda p, h: _has_any(p, ["lên lịch", "lên kế hoạch", "lịch học", "tuần này"]) and _has_any(p, ["tài liệu", "điểm kém", "điểm thấp", "yếu nhất"]),
        "build": _build_eval_doc_then_plan,
    },
    {
        "key": "content_eval_tutor",
        "label": "Tóm tắt tài liệu → Chấm hiểu → Gia sư thích ứng",
        "recognize": lambda p, h: _has_any(p, ["tóm tắt", "tom tat"]) and _has_any(p, ["giảng", "bài giảng", "thích ứng", "adaptive"]),
        "build": _build_content_eval_tutor,
    },
    {
        "key": "eval_tutor_assessment",
        "label": "Ôn chương yếu → Kiểm tra → Tạo đề luyện",
        "recognize": lambda p, h: _has_any(p, ["ôn", "kiem tra", "kiểm tra", "luyện"]) and _has_any(p, ["yếu", "chương", "đề luyện"]),
        "build": _build_eval_tutor_assessment,
    },
]


def _extract_token(text: str, patterns: List[str]) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_number(text: str, patterns: List[str]) -> Optional[int]:
    for pat in patterns:
        m = re.search(pat, _norm(text))
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def _plan(prompt: str, hub: str) -> Dict[str, Any]:
    """Match the prompt against demo scenarios -> (scenario, DAG)."""
    for scenario in _SCENARIOS:
        try:
            if scenario["recognize"](prompt, hub):
                return {"scenario_key": scenario["key"], "scenario_label": scenario["label"], "dag": scenario["build"](prompt, hub)}
        except Exception:
            continue
    # Fallback: single-intent, no coordination needed.
    return {
        "scenario_key": "single_intent",
        "scenario_label": "Đơn ý định — xử lý trực tiếp, không cần phối hợp",
        "dag": [
            {
                "step": 1,
                "from_agent": f"{hub} Hub",
                "to_agent": "EvaluationAgent",
                "task_id": "T1",
                "intent": "respond",
                "message": "Yêu cầu đơn ý định: Hub xử lý trực tiếp mà không cần phân rã.",
                "artifact": {"name": "DirectReply", "payload": {}},
            }
        ],
    }


# --------------------------------------------------------------------------- #
#  Layer 3 — Simulator: walk the DAG -> A2A lifecycle events                   #
# --------------------------------------------------------------------------- #
def _simulate(dag: List[Dict[str, Any]], hub: str) -> List[Dict[str, Any]]:
    """Emit lifecycle events (submitted -> working -> completed) per task."""
    events: List[Dict[str, Any]] = []
    base = 0
    for task in dag:
        task_id = task["task_id"]
        from_a = task["from_agent"]
        to_a = task["to_agent"]
        depends = task.get("depends_on")

        if depends:
            events.append({
                "step": base + 1,
                "phase": "handoff",
                "status": "info",
                "from_agent": from_a,
                "to_agent": to_a,
                "task_id": task_id,
                "depends_on": depends,
                "message": f"Nhận artifact từ {depends} làm đầu vào — kế thừa kết quả của tác tử trước.",
                "artifact": None,
                "ts": _ts(),
            })
            base += 1

        events.append({
            "step": base + 1,
            "phase": "submitted",
            "status": "submitted",
            "from_agent": from_a,
            "to_agent": to_a,
            "task_id": task_id,
            "depends_on": depends,
            "message": task["message"],
            "artifact": None,
            "ts": _ts(),
        })
        base += 1

        events.append({
            "step": base + 1,
            "phase": "working",
            "status": "working",
            "from_agent": to_a,
            "to_agent": to_a,
            "task_id": task_id,
            "depends_on": depends,
            "message": f"{to_a} đang xử lý: {task['intent']}.",
            "artifact": None,
            "ts": _ts(),
        })
        base += 1

        events.append({
            "step": base + 1,
            "phase": "completed",
            "status": "completed",
            "from_agent": to_a,
            "to_agent": from_a,
            "task_id": task_id,
            "depends_on": depends,
            "message": f"Hoàn thành, trả về artifact.",
            "artifact": task["artifact"],
            "ts": _ts(),
        })
        base += 1

    return events


def _ts() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _build_final_reply(scenario_key: str, hub: str, dag: List[Dict[str, Any]]) -> str:
    hub_label = HUBS[hub]["name"]
    last = dag[-1]
    art = (last.get("artifact") or {}).get("name", "kết quả")
    if scenario_key == "eval_then_plan":
        return f"{hub_label} đã phối hợp EvaluationAgent và PlanningAgent. Đã sẵn sàng kế hoạch cải thiện cho sinh viên dựa trên các môn điểm thấp."
    if scenario_key == "eval_then_exam":
        return f"{hub_label} đã phối hợp EvaluationAgent và AssessmentAgent. Đề thi đã được sinh theo môn yếu nhất."
    if scenario_key == "eval_doc_then_plan":
        return f"{hub_label} đã phối hợp EvaluationAgent và PlanningAgent. Đã lên lịch học tài liệu yếu nhất trong tuần này."
    if scenario_key == "content_eval_tutor":
        return f"{hub_label} đã phối hợp 3 tác tử (Content → Evaluation → Tutor). Đã sẵn sàng bài giảng thích ứng cho chủ đề yếu."
    if scenario_key == "eval_tutor_assessment":
        return f"{hub_label} đã phối hợp Evaluation → Tutor → Assessment. Đã ôn lại chủ đề yếu và sinh đề luyện tập."
    return f"{hub_label} xử lý trực tiếp yêu cầu đơn ý định (không cần phối hợp). Artifact: {art}."


# --------------------------------------------------------------------------- #
#  Schemas                                                                     #
# --------------------------------------------------------------------------- #
class TraceRequest(BaseModel):
    prompt: str
    hub: str = "nova"  # "nova" (giảng viên) | "orbit" (sinh viên)


class AgentCardModel(BaseModel):
    name: str
    role: str
    family: str
    capabilities: List[str]
    artifact: str
    description: str
    color: str


# --------------------------------------------------------------------------- #
#  Endpoints                                                                   #
# --------------------------------------------------------------------------- #
@router.get("/cards")
def list_agent_cards():
    """Layer 1 — expose every sub-agent's capability card (A2A discovery)."""
    return {"cards": list(_AGENT_CARDS.values()), "hubs": HUBS}


@router.get("/scenarios")
def list_scenarios():
    """Expose the demo scenarios so the UI can offer one-click prompt samples."""
    samples = {
        "eval_then_plan": "Đánh giá sinh viên A rồi lập kế hoạch cải thiện các môn điểm thấp",
        "eval_then_exam": "Tìm môn mà lớp IT1 có điểm thấp rồi tạo đề trắc nghiệm 20 câu 2 mã đề cho tôi",
        "eval_doc_then_plan": "Tìm tài liệu tôi có điểm kém nhất và lên lịch cho tôi học nó trong tuần này",
        "content_eval_tutor": "Tóm tắt tài liệu CSDL, chấm mức độ hiểu, rồi đưa bài giảng thích ứng cho tôi",
        "eval_tutor_assessment": "Ôn lại chương yếu, kiểm tra, rồi tạo đề luyện tập cho tôi",
    }
    return {
        "scenarios": [
            {"key": s["key"], "label": s["label"], "sample_prompt": samples.get(s["key"], "")}
            for s in _SCENARIOS
        ]
    }


@router.post("/trace")
def trace(req: TraceRequest):
    """Main entry: prompt -> planned DAG -> simulated A2A lifecycle events."""
    hub = req.hub.strip().lower()
    if hub not in HUBS:
        hub = "nova"

    plan = _plan(req.prompt, hub)
    events = _simulate(plan["dag"], hub)
    final_reply = _build_final_reply(plan["scenario_key"], hub, plan["dag"])

    return {
        "hub": hub,
        "hub_label": HUBS[hub]["name"],
        "prompt": req.prompt,
        "scenario_key": plan["scenario_key"],
        "scenario_label": plan["scenario_label"],
        "dag": plan["dag"],
        "events": events,
        "final_reply": final_reply,
        "protocol": "A2A (Agent2Agent) — simulated",
    }
