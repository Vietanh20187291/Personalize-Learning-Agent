from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from db import models


def resolve_subject_id(db: Session, subject_name: str) -> Optional[int]:
    name = (subject_name or "").strip()
    if not name:
        return None
    subject = db.query(models.Subject).filter(models.Subject.name.ilike(name)).first()
    return subject.id if subject else None


def get_document_score_attempts(
    db: Session,
    user_id: int,
    subject_id: Optional[int] = None,
    class_id: Optional[int] = None,
    document_id: Optional[int] = None,
    exclude_baseline: bool = True,
) -> List[models.StudentDocumentScoreHistory]:
    query = db.query(models.StudentDocumentScoreHistory).filter(
        models.StudentDocumentScoreHistory.user_id == user_id,
    )

    if subject_id is not None:
        query = query.filter(models.StudentDocumentScoreHistory.subject_id == subject_id)
    if class_id is not None:
        query = query.filter(models.StudentDocumentScoreHistory.class_id == class_id)
    if document_id is not None:
        query = query.filter(models.StudentDocumentScoreHistory.document_id == document_id)
    if exclude_baseline:
        query = query.filter(models.StudentDocumentScoreHistory.test_type != "baseline")

    return query.order_by(models.StudentDocumentScoreHistory.tested_at.asc()).all()


def latest_attempts_by_document(
    attempts: List[models.StudentDocumentScoreHistory],
) -> Dict[int, models.StudentDocumentScoreHistory]:
    latest: Dict[int, models.StudentDocumentScoreHistory] = {}
    for item in attempts:
        latest[item.document_id] = item
    return latest


def compute_test_score_from_attempts(attempts: List[models.StudentDocumentScoreHistory]) -> float:
    latest = latest_attempts_by_document(attempts)
    if not latest:
        return 0.0
    values = [float(item.score or 0.0) for item in latest.values()]
    return round(sum(values) / len(values), 2)


def _linear_slope(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0

    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    numerator = 0.0
    denominator = 0.0
    for idx, val in enumerate(values):
        dx = idx - x_mean
        numerator += dx * (val - y_mean)
        denominator += dx * dx

    if denominator <= 0:
        return 0.0
    return numerator / denominator


def compute_progress_score_from_attempts(attempts: List[models.StudentDocumentScoreHistory]) -> float:
    if not attempts:
        return 0.0

    grouped: Dict[int, List[models.StudentDocumentScoreHistory]] = defaultdict(list)
    for item in attempts:
        grouped[item.document_id].append(item)

    deltas: List[float] = []
    all_scores: List[float] = []

    for doc_attempts in grouped.values():
        ordered = sorted(doc_attempts, key=lambda row: row.tested_at or datetime.min)
        scores = [float(row.score or 0.0) for row in ordered]
        all_scores.extend(scores)
        if len(scores) >= 2:
            deltas.append(scores[-1] - scores[0])

    mean_delta = (sum(deltas) / len(deltas)) if deltas else 0.0
    slope = _linear_slope(all_scores)

    # Neutral starts at 50. Positive trend and positive delta raise score, negative trend lowers score.
    progress = 50.0 + (mean_delta * 1.8) + (slope * 8.0)
    progress = max(0.0, min(100.0, progress))
    return round(progress, 2)


def compute_improvement_signal(attempts: List[models.StudentDocumentScoreHistory]) -> float:
    grouped: Dict[int, List[models.StudentDocumentScoreHistory]] = defaultdict(list)
    for item in attempts:
        grouped[item.document_id].append(item)

    deltas: List[float] = []
    for doc_attempts in grouped.values():
        ordered = sorted(doc_attempts, key=lambda row: row.tested_at or datetime.min)
        if len(ordered) < 2:
            continue
        deltas.append(float(ordered[-1].score or 0.0) - float(ordered[0].score or 0.0))

    if not deltas:
        return 0.0
    return round(sum(deltas) / len(deltas), 2)


def compute_subject_score_metrics(
    db: Session,
    user_id: int,
    subject_id: Optional[int] = None,
    subject_name: Optional[str] = None,
    class_id: Optional[int] = None,
) -> Dict[str, float]:
    resolved_subject_id = subject_id
    if resolved_subject_id is None and subject_name:
        resolved_subject_id = resolve_subject_id(db, subject_name)

    attempts = get_document_score_attempts(
        db=db,
        user_id=user_id,
        subject_id=resolved_subject_id,
        class_id=class_id,
        exclude_baseline=True,
    )

    test_score = compute_test_score_from_attempts(attempts)
    progress_score = compute_progress_score_from_attempts(attempts)
    improvement = compute_improvement_signal(attempts)

    latest = latest_attempts_by_document(attempts)
    passed_documents = len([item for item in latest.values() if float(item.score or 0.0) >= 60.0])

    return {
        "test_score": round(test_score, 2),
        "progress_score": round(progress_score, 2),
        "improvement": round(improvement, 2),
        "attempts_total": float(len(attempts)),
        "documents_covered": float(len(latest)),
        "passed_documents": float(passed_documents),
    }
