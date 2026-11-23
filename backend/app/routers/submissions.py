"""Review, approve, export, re-run (FR-4.5.x, FR-4.7.x, BR-1)."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import can_approve, current_user, require_assignment, require_submission
from ..errors import ApiError, conflict, forbidden
from ..models import (
    BUSY_STATUSES,
    Q_DISCARDED,
    S_APPROVED,
    S_DRAFT,
    S_UPLOADED,
    User,
)
from ..queue import enqueue
from ..schemas import SubmissionDetailOut
from ..services import export
from ..services.analysis import syntax_check

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("/{submission_id}", response_model=SubmissionDetailOut)
def get_submission(submission_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return require_submission(db, user, submission_id)


@router.post("/{submission_id}/approve")
def approve(submission_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sub = require_submission(db, user, submission_id)
    if not can_approve(db, user, sub):
        raise forbidden("Only the instructor can approve a question set (BR-1)")
    if sub.status == S_APPROVED:
        raise conflict("This question set is already approved", "ALREADY_APPROVED")
    if sub.status != S_DRAFT:
        raise conflict(f"Cannot approve a submission in status {sub.status}", "NOT_READY")
    if not any(q.state != Q_DISCARDED for q in sub.questions):
        raise conflict("Keep at least one question before approving", "NO_QUESTIONS")
    sub.status = S_APPROVED
    sub.approved_by = user.id
    sub.approved_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": sub.id, "status": sub.status}


@router.post("/{submission_id}/reanalyse", status_code=202)
def reanalyse(submission_id: str, background: BackgroundTasks, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    """Re-run analysis + generation (e.g. after FAILED or a threshold change). Replaces the draft set."""
    sub = require_submission(db, user, submission_id)
    if sub.status == S_APPROVED:
        raise conflict("Approved question sets are locked", "LOCKED")
    if sub.status in BUSY_STATUSES:
        raise conflict("This submission is already being processed", "BUSY")
    err = syntax_check(sub.code)
    if err:
        sub.error = err
        db.commit()
        raise ApiError(422, "PARSE_FAILED", err)
    sub.status, sub.error = S_UPLOADED, None
    db.commit()
    enqueue([sub.id], background)
    return {"job_id": sub.id}


@router.delete("/{submission_id}", status_code=204)
def delete_submission(submission_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sub = require_submission(db, user, submission_id)
    require_assignment(db, user, sub.assignment_id, instructor_only=True)
    db.delete(sub)
    db.commit()


@router.get("/{submission_id}/export")
def export_submission(submission_id: str, format: Literal["pdf", "csv"] = Query("pdf"),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    sub = require_submission(db, user, submission_id)
    if sub.status != S_APPROVED:
        raise conflict("Only approved question sets can be exported", "NOT_APPROVED")
    base = f"viva_{sub.student_ref}_{sub.assignment.title}".replace(" ", "_")[:80]
    base = "".join(c for c in base if c.isalnum() or c in "_-.")
    if format == "csv":
        return Response(export.to_csv(sub), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{base}.csv"'})
    approver = db.get(User, sub.approved_by) if sub.approved_by else None
    return Response(export.to_pdf(sub, approver.email if approver else None), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{base}.pdf"'})
