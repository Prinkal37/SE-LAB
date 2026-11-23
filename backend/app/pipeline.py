"""The background job: AST analysis -> question generation (runs in the RQ worker or inline).

UPLOADED -> ANALYSING -> GENERATING -> DRAFT        (happy path)
                     \\-> PARSE_FAILED               (FR-4.6.1)
         any error  ---> FAILED
"""
import logging

from sqlalchemy.orm import Session

from . import db as dbmod
from .models import (
    Q_DRAFT,
    S_ANALYSING,
    S_DRAFT,
    S_FAILED,
    S_GENERATING,
    S_PARSE_FAILED,
    Finding,
    Question,
    Submission,
)
from .config import get_settings
from .services import analysis, questions

log = logging.getLogger("avg.pipeline")


def _n_questions(sub: Submission) -> int:
    s = get_settings()
    return sub.assignment.num_questions or s.max_questions


def process_submission(submission_id: str) -> str:
    db: Session = dbmod.SessionLocal()
    try:
        sub = db.get(Submission, submission_id)
        if sub is None:
            return "missing"
        try:
            sub.status, sub.error = S_ANALYSING, None
            db.commit()

            result = analysis.analyse(sub.code)
            sub.analysis = result.raw
            if not result.success:
                sub.status, sub.error = S_PARSE_FAILED, result.syntax_error
                db.commit()
                return sub.status

            # replace any previous results (re-run)
            sub.findings.clear()
            sub.questions.clear()
            db.flush()

            rows: dict[str, Finding] = {}
            for f in result.findings:
                row = Finding(detector=f.detector, name=f.name, start_line=f.start_line, end_line=f.end_line,
                              node_type=f.node_type, reason=f.reason, severity=f.severity)
                sub.findings.append(row)
                rows[f.key] = row
            sub.status = S_GENERATING
            db.commit()

            targets = analysis.pick_targets(result.findings, result.functions, _n_questions(sub))
            generated, gen_name = questions.generate(targets, sub.code)
            by_key = {t.key: t for t in targets}
            for pos, q in enumerate(generated):
                t = by_key[q.target_key]
                sub.questions.append(Question(
                    finding=rows.get(t.key), position=pos, question_text=q.question_text,
                    related_line=q.related_line, related_node_type=q.related_node_type,
                    difficulty=q.difficulty if q.difficulty in ("easy", "medium", "hard") else "medium",
                    state=Q_DRAFT, target=None if t.key in rows else t.as_target()))
            sub.generator = gen_name
            sub.status = S_DRAFT
            db.commit()
            return sub.status
        except Exception as e:  # never leave a submission stuck in a busy state
            log.exception("Processing submission %s failed", submission_id)
            db.rollback()
            sub = db.get(Submission, submission_id)
            if sub:
                sub.status, sub.error = S_FAILED, f"Processing failed: {e}"
                db.commit()
            return S_FAILED
    finally:
        db.close()


def regenerate_question(db: Session, q: Question) -> Question:
    """FR-4.5.4: new question for one flagged element, the rest of the set untouched."""
    sub = q.submission
    if q.finding is not None:
        f = q.finding
        target = analysis.FindingData(f.detector, f.name, f.start_line, f.end_line, f.node_type, f.reason,
                                      f.severity, key="t1")
    elif q.target:
        target = analysis.FindingData(**{**q.target, "key": "t1"})
    else:
        target = analysis.FindingData("general", None, q.related_line, q.related_line, q.related_node_type,
                                      "General comprehension.", key="t1")
    variant = (q.position or 0) + 1 + (len(q.question_text) % 3)
    generated, gen_name = questions.generate([target], sub.code, avoid=q.question_text, variant=variant)
    new = generated[0]
    q.question_text = new.question_text
    q.related_line = new.related_line
    q.related_node_type = new.related_node_type
    q.difficulty = new.difficulty if new.difficulty in ("easy", "medium", "hard") else q.difficulty
    q.state = Q_DRAFT
    db.commit()
    return q
