"""Assignment details + submission upload/list (FR-4.2.x)."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user, require_assignment
from ..errors import ApiError, bad_request
from ..models import S_PARSE_FAILED, S_UPLOADED, Assignment, Submission, User
from ..queue import enqueue
from ..schemas import AssignmentOut, AssignmentUpdate, SubmissionOut, UploadOut
from ..services import uploads
from ..services.analysis import syntax_check

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return require_assignment(db, user, assignment_id)


@router.patch("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(assignment_id: str, body: AssignmentUpdate, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    a = require_assignment(db, user, assignment_id, instructor_only=True)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit()
    return a


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(assignment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(require_assignment(db, user, assignment_id, instructor_only=True))
    db.commit()


@router.get("/{assignment_id}/submissions", response_model=list[SubmissionOut])
def list_submissions(assignment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_assignment(db, user, assignment_id)
    return db.scalars(
        select(Submission).where(Submission.assignment_id == assignment_id).order_by(Submission.created_at)
    ).all()


@router.post("/{assignment_id}/submissions", response_model=UploadOut, status_code=202)
async def upload_submission(
    assignment_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    student_ref: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Instructors and TAs (BR-2) upload a .py (one student) or .zip (batch). Returns 202 + a job id;
    processing happens in the background and the UI polls the submission status."""
    a: Assignment = require_assignment(db, user, assignment_id)
    s = get_settings()
    name = file.filename or ""
    limit = s.max_zip_bytes if name.lower().endswith(".zip") else s.max_file_bytes
    data = await file.read(limit + 1)

    if name.lower().endswith(".py"):
        files, rejected = [uploads.from_single(name, data, student_ref)], []
    elif name.lower().endswith(".zip"):
        files, rejected = uploads.from_zip(data)
    else:
        raise bad_request("Only .py or .zip files are allowed.", "UNSUPPORTED_FILE")

    if not files:
        raise ApiError(400, "NOTHING_TO_PROCESS", "; ".join(f"{r['file']}: {r['reason']}" for r in rejected)
                       or "No usable files in upload.")

    batch_id = uuid.uuid4().hex
    to_queue, ids = [], []
    for f in files:
        err = syntax_check(f.code)  # FR-4.2.4: reject before full analysis, but keep a visible record
        sub = Submission(assignment_id=a.id, student_ref=f.student_ref, filename=f.filename, code=f.code,
                         status=S_PARSE_FAILED if err else S_UPLOADED, error=err, batch_id=batch_id,
                         uploaded_by=user.id)
        db.add(sub)
        db.flush()
        ids.append(sub.id)
        if not err:
            to_queue.append(sub.id)
    db.commit()

    enqueue(to_queue, background)
    return UploadOut(job_id=ids[0] if len(ids) == 1 else batch_id, submission_ids=ids, rejected=rejected)
