

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_teacher
from backend.app.models.attempt import AttemptAnswer, QuizAttempt
from backend.app.models.notification import Notification, NotificationType
from backend.app.models.quiz import (
    Question,
    QuestionOption,
    Quiz,
    QuizEnrollment,
    QuizStatus,
)
from backend.app.models.user import User, UserRole
from backend.app.schemas.quiz import (
    OptionOut,
    OptionOutPublic,
    QuizCreate,
    QuizDetail,
    QuizPublic,
    QuizSummary,
    QuizUpdate,
    QuestionOut,
    QuestionOutPublic,
)

router = APIRouter()


# ── Local Pydantic models for enrollment ────────────────────────────────────

class EnrollRequest(BaseModel):
    user_ids: List[int]


class EnrollmentStudentOut(BaseModel):
    id: int
    full_name: str
    email: str
    enrolled_at: datetime
    model_config = {"from_attributes": True}


class EnrollmentResult(BaseModel):
    enrolled: List[int]
    already_enrolled: List[int]
    not_found: List[int]
    message: str


class SubmitPayload(BaseModel):
    answers: List[dict]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _assert_owner_or_admin(quiz: Quiz, user: User) -> None:
    if user.role == UserRole.admin:
        return
    if quiz.creator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this quiz.",
        )


def _quiz_summary(quiz: Quiz, uid: int) -> dict:
    now = datetime.now(timezone.utc)
    quiz_dt = None
    if quiz.scheduled_date:
        quiz_dt = datetime.combine(
            quiz.scheduled_date,
            quiz.scheduled_time or datetime.min.time(),
        ).replace(tzinfo=timezone.utc)

    done = next(
        (a for a in (quiz.attempts or []) if a.user_id == uid and a.is_completed),
        None,
    )

    if done:
        computed = QuizStatus.completed
    elif quiz_dt and now < quiz_dt:
        computed = QuizStatus.upcoming
    else:
        computed = QuizStatus.active

    return {
        "id": quiz.id,
        "title": quiz.title,
        "category": quiz.category,
        "status": computed,
        "duration_mins": quiz.duration_mins,
        "total_points": quiz.total_points,
        "scheduled_date": quiz.scheduled_date,
        "scheduled_time": quiz.scheduled_time,
        "enrolled_count": len(quiz.enrollments or []),
        "creator_name": quiz.creator.full_name if quiz.creator else "Unknown",
        "created_at": quiz.created_at,
        "is_attempted": bool(done),
    }


# ── List quizzes ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[QuizSummary])
def list_quizzes(
    search: Optional[str] = Query(None, max_length=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Role-aware:
    - teacher/admin → quizzes they created
    - student       → quizzes they are enrolled in
    """
    if current_user.role in (UserRole.admin, UserRole.teacher):
        query = db.query(Quiz).filter(Quiz.creator_id == current_user.id)
    else:
        enrolled_ids = [
            e.quiz_id
            for e in db.query(QuizEnrollment)
            .filter(QuizEnrollment.user_id == current_user.id)
            .all()
        ]
        if not enrolled_ids:
            return []
        query = db.query(Quiz).filter(Quiz.id.in_(enrolled_ids))

    quizzes = query.order_by(Quiz.created_at.desc()).all()
    summaries = [_quiz_summary(q, current_user.id) for q in quizzes]

    if search:
        s = search.lower()
        summaries = [
            q for q in summaries
            if s in q["title"].lower()
            or s in (
                q["category"].value
                if hasattr(q["category"], "value")
                else str(q["category"])
            ).lower()
        ]

    if status_filter:
        summaries = [
            q for q in summaries
            if (q["status"].value if hasattr(q["status"], "value") else q["status"])
            == status_filter
        ]

    return summaries


# ── Create quiz ──────────────────────────────────────────────────────────────

@router.post("", response_model=QuizSummary, status_code=status.HTTP_201_CREATED)
def create_quiz(
    payload: QuizCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    """Create a quiz with questions/options. Optionally enroll students immediately."""
    quiz = Quiz(
        title=payload.title,
        category=payload.category,
        duration_mins=payload.duration_mins,
        total_points=payload.total_points,
        scheduled_date=payload.scheduled_date,
        scheduled_time=payload.scheduled_time,
        status=QuizStatus.upcoming,
        creator_id=current_user.id,
    )
    db.add(quiz)
    db.flush()

    for q_data in payload.questions:
        question = Question(quiz_id=quiz.id, text=q_data.text, order=q_data.order)
        db.add(question)
        db.flush()
        for opt in q_data.options:
            db.add(QuestionOption(
                question_id=question.id,
                text=opt.text,
                is_correct=opt.is_correct,
                order=opt.order,
            ))

    db.flush()

    # Optional: enroll students immediately on creation
    if payload.student_ids:
        for uid in set(payload.student_ids):
            student = db.query(User).filter(
                User.id == uid, User.role == UserRole.student, User.is_active == True
            ).first()
            if not student:
                continue
            exists = db.query(QuizEnrollment).filter(
                QuizEnrollment.quiz_id == quiz.id,
                QuizEnrollment.user_id == uid,
            ).first()
            if exists:
                continue
            db.add(QuizEnrollment(quiz_id=quiz.id, user_id=uid))
            db.add(Notification(
                user_id=uid,
                type=NotificationType.quiz_assigned,
                title="New Quiz Assigned",
                message=(
                    f"You have been enrolled in '{quiz.title}' "
                    f"by {current_user.full_name}. Good luck!"
                ),
            ))

    db.commit()
    db.refresh(quiz)
    return _quiz_summary(quiz, current_user.id)


# ── Get quiz detail ──────────────────────────────────────────────────────────

@router.get("/{quiz_id}", response_model=QuizDetail)
def get_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    if current_user.role == UserRole.student:
        enrolled = db.query(QuizEnrollment).filter(
            QuizEnrollment.quiz_id == quiz_id,
            QuizEnrollment.user_id == current_user.id,
        ).first()
        if not enrolled:
            raise HTTPException(
                status_code=403,
                detail="You are not enrolled in this quiz.",
            )

    questions_out = [
        QuestionOut(
            id=q.id,
            text=q.text,
            order=q.order,
            options=[
                OptionOut(id=o.id, text=o.text, is_correct=o.is_correct, order=o.order)
                for o in sorted(q.options, key=lambda x: x.order)
            ],
        )
        for q in sorted(quiz.questions, key=lambda x: x.order)
    ]

    return QuizDetail(
        id=quiz.id,
        title=quiz.title,
        category=quiz.category,
        status=quiz.status,
        duration_mins=quiz.duration_mins,
        total_points=quiz.total_points,
        scheduled_date=quiz.scheduled_date,
        scheduled_time=quiz.scheduled_time,
        enrolled_count=len(quiz.enrollments or []),
        creator_name=quiz.creator.full_name if quiz.creator else "Unknown",
        created_at=quiz.created_at,
        questions=questions_out,
    )


# ── Update quiz ──────────────────────────────────────────────────────────────

@router.patch("/{quiz_id}", response_model=QuizSummary)
def update_quiz(
    quiz_id: int,
    payload: QuizUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    _assert_owner_or_admin(quiz, current_user)

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(quiz, field, value)

    db.commit()
    db.refresh(quiz)
    return _quiz_summary(quiz, current_user.id)


# ── Delete quiz ──────────────────────────────────────────────────────────────

@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    _assert_owner_or_admin(quiz, current_user)
    db.delete(quiz)
    db.commit()


# ── Take quiz (student) ──────────────────────────────────────────────────────

@router.get("/{quiz_id}/take", response_model=QuizPublic)
def take_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a quiz for the student to take.
    Validates enrollment, completion status, and schedule.
    """
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    if current_user.role in (UserRole.admin, UserRole.teacher):
        # Teachers/admins preview their own quizzes
        if quiz.creator_id != current_user.id and current_user.role != UserRole.admin:
            raise HTTPException(
                status_code=403,
                detail="You can only preview quizzes you created.",
            )
    else:
        # Student checks
        enrolled = db.query(QuizEnrollment).filter(
            QuizEnrollment.quiz_id == quiz_id,
            QuizEnrollment.user_id == current_user.id,
        ).first()
        if not enrolled:
            raise HTTPException(
                status_code=403,
                detail="You are not enrolled in this quiz. Contact your teacher.",
            )

        completed = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == True,
        ).first()
        if completed:
            raise HTTPException(
                status_code=409,
                detail="You have already completed this quiz.",
            )

        # Scheduled but not yet open
        if quiz.scheduled_date:
            quiz_dt = datetime.combine(
                quiz.scheduled_date,
                quiz.scheduled_time or datetime.min.time(),
            ).replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < quiz_dt:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"This quiz is not yet available. "
                        f"It starts at {quiz_dt.strftime('%d %b %Y, %H:%M')} UTC."
                    ),
                )

        # Create or resume in-progress attempt
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == False,
        ).first()
        if not attempt:
            attempt = QuizAttempt(user_id=current_user.id, quiz_id=quiz_id)
            db.add(attempt)
            db.commit()

    questions_out = [
        QuestionOutPublic(
            id=q.id,
            text=q.text,
            order=q.order,
            options=[
                OptionOutPublic(id=o.id, text=o.text, order=o.order)
                for o in sorted(q.options, key=lambda x: x.order)
            ],
        )
        for q in sorted(quiz.questions, key=lambda x: x.order)
    ]

    return QuizPublic(
        id=quiz.id,
        title=quiz.title,
        category=quiz.category,
        duration_mins=quiz.duration_mins,
        total_points=quiz.total_points,
        questions=questions_out,
    )


# ── Submit quiz ──────────────────────────────────────────────────────────────

@router.post("/{quiz_id}/submit")
def submit_quiz(
    quiz_id: int,
    payload: SubmitPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Score and persist a quiz submission."""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    if current_user.role == UserRole.student:
        enrolled = db.query(QuizEnrollment).filter(
            QuizEnrollment.quiz_id == quiz_id,
            QuizEnrollment.user_id == current_user.id,
        ).first()
        if not enrolled:
            raise HTTPException(status_code=403, detail="You are not enrolled in this quiz.")

        already = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.is_completed == True,
        ).first()
        if already:
            raise HTTPException(status_code=409, detail="You have already submitted this quiz.")

    if not payload.answers:
        raise HTTPException(
            status_code=422,
            detail="No answers provided. Please answer at least one question.",
        )

    # Find or create attempt
    attempt = db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz_id,
        QuizAttempt.user_id == current_user.id,
        QuizAttempt.is_completed == False,
    ).first()
    if not attempt:
        attempt = QuizAttempt(user_id=current_user.id, quiz_id=quiz_id)
        db.add(attempt)
        db.flush()

    # Build lookup maps
    questions = {q.id: q for q in quiz.questions}
    all_options = {o.id: o for q in quiz.questions for o in q.options}

    correct_count = 0
    seen_qids: set = set()

    for ans in payload.answers:
        qid = ans.get("question_id")
        oid = ans.get("selected_option_id")

        if not isinstance(qid, int) or qid not in questions:
            continue
        if qid in seen_qids:
            continue

        option = all_options.get(oid) if isinstance(oid, int) else None
        is_correct = bool(option and option.is_correct and option.question_id == qid)
        if is_correct:
            correct_count += 1

        db.add(AttemptAnswer(
            attempt_id=attempt.id,
            question_id=qid,
            selected_option_id=oid,
            is_correct=is_correct,
        ))
        seen_qids.add(qid)

    total_questions = len(quiz.questions)
    score_pct = round((correct_count / total_questions * 100), 1) if total_questions else 0.0
    score     = round((score_pct / 100) * quiz.total_points, 1)
    passed    = score_pct >= 60

    attempt.score        = score
    attempt.score_pct    = score_pct
    attempt.is_completed = True
    attempt.completed_at = datetime.now(timezone.utc)

    # Notification
    if score_pct == 100:
        notif = Notification(
            user_id=current_user.id,
            type=NotificationType.achievement,
            title="🏆 Perfect Score!",
            message=f"You scored 100% in '{quiz.title}'. Outstanding!",
        )
    elif passed:
        notif = Notification(
            user_id=current_user.id,
            type=NotificationType.performance,
            title="✅ Quiz Passed!",
            message=f"You passed '{quiz.title}' with {score_pct}%. Keep it up!",
        )
    else:
        notif = Notification(
            user_id=current_user.id,
            type=NotificationType.performance,
            title="📝 Quiz Completed",
            message=f"You scored {score_pct}% in '{quiz.title}'. Review and improve!",
        )
    db.add(notif)
    db.commit()

    return {
        "quiz_title":      quiz.title,
        "score_pct":       score_pct,
        "score":           score,
        "correct_count":   correct_count,
        "total_questions": total_questions,
        "passed":          passed,
    }


# ── Bulk-enroll students ─────────────────────────────────────────────────────

@router.post("/{quiz_id}/enroll", response_model=EnrollmentResult)
def enroll_students(
    quiz_id: int,
    payload: EnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    """Bulk-enroll students. Skips invalid / already-enrolled IDs gracefully."""
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    _assert_owner_or_admin(quiz, current_user)

    if not payload.user_ids:
        raise HTTPException(status_code=422, detail="No user IDs provided.")

    enrolled: List[int] = []
    already_enrolled: List[int] = []
    not_found: List[int] = []

    for uid in set(payload.user_ids):
        student = db.query(User).filter(
            User.id == uid,
            User.role == UserRole.student,
            User.is_active == True,
        ).first()
        if not student:
            not_found.append(uid)
            continue

        existing = db.query(QuizEnrollment).filter(
            QuizEnrollment.quiz_id == quiz_id,
            QuizEnrollment.user_id == uid,
        ).first()
        if existing:
            already_enrolled.append(uid)
            continue

        db.add(QuizEnrollment(quiz_id=quiz_id, user_id=uid))
        db.add(Notification(
            user_id=uid,
            type=NotificationType.quiz_assigned,
            title="New Quiz Assigned",
            message=(
                f"You have been enrolled in '{quiz.title}' "
                f"by {current_user.full_name}. Good luck!"
            ),
        ))
        enrolled.append(uid)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Enrollment conflict. Some students may already be enrolled.",
        )

    parts = []
    if enrolled:
        parts.append(f"{len(enrolled)} enrolled")
    if already_enrolled:
        parts.append(f"{len(already_enrolled)} already enrolled")
    if not_found:
        parts.append(f"{len(not_found)} not found / not a student")

    return EnrollmentResult(
        enrolled=enrolled,
        already_enrolled=already_enrolled,
        not_found=not_found,
        message=", ".join(parts) or "No changes made.",
    )


# ── Remove enrollment ────────────────────────────────────────────────────────

@router.delete("/{quiz_id}/enroll/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_enrollment(
    quiz_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    _assert_owner_or_admin(quiz, current_user)

    enrollment = db.query(QuizEnrollment).filter(
        QuizEnrollment.quiz_id == quiz_id,
        QuizEnrollment.user_id == user_id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found.")

    db.delete(enrollment)
    db.commit()


# ── List enrolled students ───────────────────────────────────────────────────

@router.get("/{quiz_id}/students", response_model=List[EnrollmentStudentOut])
def list_enrolled_students(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    _assert_owner_or_admin(quiz, current_user)

    enrollments = (
        db.query(QuizEnrollment)
        .filter(QuizEnrollment.quiz_id == quiz_id)
        .order_by(QuizEnrollment.enrolled_at.asc())
        .all()
    )

    return [
        EnrollmentStudentOut(
            id=e.user.id,
            full_name=e.user.full_name,
            email=e.user.email,
            enrolled_at=e.enrolled_at,
        )
        for e in enrollments
        if e.user
    ]
