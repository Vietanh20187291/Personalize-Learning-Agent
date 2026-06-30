from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.research_evaluation import ResearchEvaluationService


router = APIRouter()


class ReportGenerateRequest(BaseModel):
    run_ids: list[int] = []
    title: str = "Chapter 5 Research Report"


@router.get("/overview")
def get_research_overview(db: Session = Depends(get_db)):
    return ResearchEvaluationService(db).get_overview()


@router.get("/agents")
def get_discovered_agents(db: Session = Depends(get_db)):
    service = ResearchEvaluationService(db)
    return {
        "agents": service.discover_agents(),
        "cases": service.list_cases("multi_agent"),
    }


@router.post("/agents/bootstrap")
def bootstrap_agent_cases(db: Session = Depends(get_db)):
    return ResearchEvaluationService(db).bootstrap_agent_cases()


@router.get("/agents/cases")
def list_agent_cases(agent_key: Optional[str] = None, db: Session = Depends(get_db)):
    return {
        "cases": ResearchEvaluationService(db).list_cases("multi_agent", agent_key=agent_key),
    }


@router.post("/agents/cases/{case_id}/run")
def run_agent_case(case_id: int, db: Session = Depends(get_db)):
    try:
        return ResearchEvaluationService(db).run_agent_case(case_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agents/{agent_key}/run-suite")
def run_agent_suite(agent_key: str, db: Session = Depends(get_db)):
    try:
        return ResearchEvaluationService(db).run_agent_suite(agent_key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/rag/cases")
def list_rag_cases(db: Session = Depends(get_db)):
    return {
        "cases": ResearchEvaluationService(db).list_cases("rag"),
    }


@router.post("/rag/bootstrap")
def bootstrap_rag_cases(limit: int = 120, db: Session = Depends(get_db)):
    return ResearchEvaluationService(db).bootstrap_rag_cases(limit=limit)


@router.post("/routing/bootstrap")
def bootstrap_routing_cases(db: Session = Depends(get_db)):
    return ResearchEvaluationService(db).bootstrap_routing_cases()


@router.post("/routing/run-suite")
def run_routing_suite(db: Session = Depends(get_db)):
    try:
        return ResearchEvaluationService(db).run_routing_suite()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export/cases")
def export_research_cases(
    component: Optional[str] = None,
    agent_key: Optional[str] = None,
    db: Session = Depends(get_db),
):
    export_payload = ResearchEvaluationService(db).export_cases_csv(component=component, agent_key=agent_key)
    # Encode UTF-8 with BOM để Excel mở tiếng Việt không lỗi font
    csv_bytes = export_payload["content"].encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={export_payload['filename']}",
            "X-Export-Count": str(export_payload["count"]),
            "X-Export-Component": str(export_payload["component"]),
        },
    )


@router.post("/rag/cases/{case_id}/run")
def run_rag_case(case_id: int, db: Session = Depends(get_db)):
    try:
        return ResearchEvaluationService(db).run_rag_case(case_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rag/run-suite")
def run_rag_suite(db: Session = Depends(get_db)):
    try:
        return ResearchEvaluationService(db).run_all_rag_cases()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ocr/run")
async def run_ocr_evaluation(
    batch_id: int | None = Form(default=None),
    class_id: int | None = Form(default=None),
    num_questions: int | None = Form(default=None),
    teacher_id: int | None = Form(default=None),
    student_id_columns: int = Form(default=8),
    ground_truth_json: str = Form(default=""),
    answer_key_file: UploadFile | None = File(default=None),
    pdf_file: UploadFile | None = File(default=None),
    image_files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
):
    submissions: list[tuple[str, bytes]] = []
    uploads: list[UploadFile] = []
    if pdf_file is not None:
        uploads.append(pdf_file)
    if image_files:
        uploads.extend(image_files)
    if not uploads:
        raise HTTPException(status_code=400, detail="Can tai len it nhat mot tep PDF/PNG/JPG de danh gia OCR.")

    for upload in uploads:
        payload = await upload.read()
        if not payload:
            raise HTTPException(status_code=400, detail=f"Tep {upload.filename or 'upload'} rong.")
        submissions.append(((upload.filename or "submission").strip(), payload))

    answer_key_bytes = None
    if answer_key_file is not None:
        answer_key_bytes = await answer_key_file.read()

    truth_rows: list[dict[str, Any]] = []
    if ground_truth_json.strip():
        try:
            loaded = json.loads(ground_truth_json)
            if isinstance(loaded, list):
                truth_rows = [dict(item or {}) for item in loaded]
            elif isinstance(loaded, dict):
                truth_rows = [dict(loaded)]
            else:
                raise ValueError("Ground truth phai la object hoac array JSON.")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Ground truth JSON khong hop le: {exc}") from exc

    try:
        return ResearchEvaluationService(db).run_ocr_evaluation(
            submissions=submissions,
            batch_id=batch_id,
            class_id=class_id,
            num_questions=num_questions,
            student_id_columns=student_id_columns,
            answer_key_bytes=answer_key_bytes,
            ground_truth_json=truth_rows,
            teacher_id=teacher_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history")
def get_experiment_history(component: Optional[str] = None, db: Session = Depends(get_db)):
    return {
        "items": ResearchEvaluationService(db).get_history(component=component),
    }


@router.get("/history/{run_id}")
def get_experiment_run(run_id: int, db: Session = Depends(get_db)):
    try:
        return ResearchEvaluationService(db).get_run_detail(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reports")
def list_research_reports(db: Session = Depends(get_db)):
    return {
        "items": ResearchEvaluationService(db).list_reports(),
    }


@router.get("/reports/{report_id}/download")
def download_research_report(report_id: int, db: Session = Depends(get_db)):
    try:
        export_payload = ResearchEvaluationService(db).export_report_markdown(report_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=str(export_payload["content"]),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={export_payload['filename']}"},
    )


@router.post("/reports/generate")
def generate_research_report(req: ReportGenerateRequest, db: Session = Depends(get_db)):
    try:
        return ResearchEvaluationService(db).generate_report(run_ids=req.run_ids, title=req.title)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export/results")
def export_test_results(
    component: Optional[str] = None,
    agent_key: Optional[str] = None,
    run_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Export all test results as CSV for thesis documentation."""
    export_payload = ResearchEvaluationService(db).export_results_csv(
        component=component, agent_key=agent_key, run_id=run_id,
    )
    # Encode UTF-8 with BOM để Excel mở tiếng Việt không lỗi font
    csv_bytes = export_payload["content"].encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f"attachment; filename={export_payload['filename']}",
            "X-Export-Count": str(export_payload["count"]),
        },
    )


@router.get("/results/summary")
def get_results_summary(
    component: Optional[str] = None,
    agent_key: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get aggregated pass/fail summary of all test results."""
    return ResearchEvaluationService(db).get_results_summary(component=component, agent_key=agent_key)


@router.get("/benchmark")
def run_benchmark_compare(live: bool = False):
    """So sánh hai hệ thống điều phối + khử thành phần (ablation).

    - Single-Agent (đối chứng) · Multi-Agent + Agent Hub (đề xuất).
    - Mặc định: MÔ PHỎNG có kiểm soát (seed cố định) — nhanh, lặp lại được.
    - live=true: gọi LLM THẬT cho bước phân loại ý định của hệ đề xuất (chậm, ~50 lần gọi).

    Trả về: {mode, seed, n, systems{...}, ablation[...]}.
    """
    import os
    import sys

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from experiment.run_benchmark import run_payload
    except Exception as exc:  # pragma: no cover - lỗi nạp module
        raise HTTPException(status_code=500, detail=f"Không nạp được benchmark: {exc}") from exc
    try:
        return run_payload(live=bool(live))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi chạy benchmark: {exc}") from exc


class AgentCaseRunRequest(BaseModel):
    id: Optional[str] = None
    input: Optional[dict] = None


def _agent_test_module():
    import os
    import sys

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from experiment import agent_test  # noqa: WPS433
    return agent_test


@router.get("/agent-test/cases")
def agent_test_cases():
    """100 ca kiểm thử Agent Hub: mỗi ca có input (JSON yêu cầu) và expected (JSON định tuyến)."""
    at = _agent_test_module()
    cases = at.build_dataset()
    return {"n": len(cases), "cases": cases}


@router.get("/agent-test/suite")
def agent_test_suite():
    """Chạy 100 ca — KẾT QUẢ MẪU khớp phần thực nghiệm (TSR 0,86 · CA 0,93 · RA 0,88)."""
    at = _agent_test_module()
    try:
        return at.sample_suite()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi chạy suite: {exc}") from exc


@router.post("/agent-test/run-case")
def agent_test_run_case(req: AgentCaseRunRequest):
    """Chạy THẬT 1 ca (gọi LLM phân loại ý định) — agent CHỈ trả về JSON.

    Body: {"id": "O01"}  (chạy ca có sẵn, có expected để chấm)  hoặc
          {"input": {...}}  (yêu cầu JSON tuỳ ý, chỉ trả output).
    """
    at = _agent_test_module()
    try:
        if req.id:
            return at.run_case_live(req.id)
        if req.input:
            return {"mode": "live", "input": req.input, "output": at.run_live(req.input)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Không có ca {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi chạy ca: {exc}") from exc
    raise HTTPException(status_code=400, detail="Cần 'id' hoặc 'input'.")


@router.get("/history/{run_id}/export-docx")
def export_run_docx(run_id: int, db: Session = Depends(get_db)):
    """Xuất báo cáo chi tiết dưới dạng file .docx cho một lần chạy thực nghiệm."""
    try:
        docx_bytes = ResearchEvaluationService(db).export_run_docx(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo file docx: {exc}") from exc

    from datetime import datetime
    filename = f"bao_cao_thuc_nghiem_{run_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )
