"""Edit / discard / regenerate one question (FR-4.5.3 - FR-4.5.5)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, require_question
from ..errors import bad_request, conflict
from ..models import Q_DISCARDED, Q_DRAFT, Q_EDITED, S_APPROVED, S_DRAFT, User
from ..pipeline import regenerate_question
from ..schemas import QuestionOut, QuestionPatch

router = APIRouter(prefix="/questions", tags=["questions"])


def _editable(q):
    if q.submission.status == S_APPROVED:
        raise conflict("Approved question sets are locked", "LOCKED")
    if q.submission.status != S_DRAFT:
        raise conflict("Questions can only be changed while the set is a draft", "NOT_DRAFT")


@router.patch("/{question_id}", response_model=QuestionOut)
def edit_question(question_id: str, body: QuestionPatch, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    q = require_question(db, user, question_id)
    _editable(q)
    if body.question_text is None and body.state is None:
        raise bad_request("Nothing to change")
    if body.question_text is not None:
        q.question_text = body.question_text.strip()
        q.state = Q_EDITED
    if body.state == Q_DISCARDED:
        q.state = Q_DISCARDED
    elif body.state == Q_DRAFT and q.state == Q_DISCARDED:  # restore
        q.state = Q_DRAFT
    db.commit()
    return q


@router.post("/{question_id}/regenerate", response_model=QuestionOut)
def regenerate(question_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = require_question(db, user, question_id)
    _editable(q)
    return regenerate_question(db, q)
