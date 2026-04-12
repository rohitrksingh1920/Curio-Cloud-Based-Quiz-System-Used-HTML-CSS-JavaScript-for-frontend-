
from datetime import date, time, datetime, timedelta, timezone

from backend.app.core.database import SessionLocal, engine, Base
from backend.app.core.security import hash_password

# Import models so Base knows about them
from backend.app.models.user import User, UserRole
from backend.app.models.quiz import Quiz, Question, QuestionOption, QuizStatus, QuizCategory
from backend.app.models.attempt import QuizAttempt, AttemptAnswer
from backend.app.models.notification import Notification, NotificationType


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(User).count() > 0:
        print("Database already seeded. Skipping.")
        db.close()
        return

    print("Seeding database…")

    # ── Users ─────────────────────────────────────────────────────────────────
    admin = User(
        full_name="Admin User",
        email="admin@projexi.com",
        hashed_password=hash_password("admin1234"),
        role=UserRole.admin,
        email_digests=True,
        push_alerts=False,
    )
    rohit = User(
        full_name="Rohit Singh",
        email="rohitrk.singh1920@gmail.com",
        hashed_password=hash_password("rohit1234"),
        role=UserRole.teacher,
        email_digests=True,
        push_alerts=False,
    )
    students = [
        User(
            full_name=name,
            email=email,
            hashed_password=hash_password("student123"),
            role=UserRole.student,
        )
        for name, email in [
            ("Alice Johnson",  "alice@example.com"),
            ("Bob Smith",      "bob@example.com"),
            ("Charlie Brown",  "charlie@example.com"),
            ("Diana Prince",   "diana@example.com"),
            ("Ethan Hunt",     "ethan@example.com"),
        ]
    ]

    db.add_all([admin, rohit] + students)
    db.flush()

    # ── Quizzes ───────────────────────────────────────────────────────────────
    quiz_data = [
        {
            "title": "Advanced Python Concepts",
            "category": QuizCategory.computer_science,
            "duration_mins": 45,
            "total_points": 100,
            "scheduled_date": date(2026, 6, 20),
            "scheduled_time": time(10, 0),
            "questions": [
                {
                    "text": "What does the GIL stand for in Python?",
                    "options": [
                        ("Global Interpreter Lock", True),
                        ("General Input Loop", False),
                        ("Global Input Library", False),
                        ("General Interpreter Layer", False),
                    ],
                },
                {
                    "text": "Which of the following is a mutable data type in Python?",
                    "options": [
                        ("Tuple", False),
                        ("String", False),
                        ("List", True),
                        ("Integer", False),
                    ],
                },
                {
                    "text": "What is a decorator in Python?",
                    "options": [
                        ("A design pattern for subclassing", False),
                        ("A function that wraps another function", True),
                        ("A built-in module for formatting", False),
                        ("A type of class method", False),
                    ],
                },
            ],
        },
        {
            "title": "World History: WWII",
            "category": QuizCategory.history,
            "duration_mins": 60,
            "total_points": 100,
            "scheduled_date": date(2026, 6, 22),
            "scheduled_time": time(14, 0),
            "questions": [
                {
                    "text": "In which year did World War II begin?",
                    "options": [
                        ("1935", False), ("1939", True), ("1941", False), ("1945", False),
                    ],
                },
                {
                    "text": "What was the code name for the Allied invasion of Normandy?",
                    "options": [
                        ("Operation Torch", False), ("Operation Overlord", True),
                        ("Operation Barbarossa", False), ("Operation Market Garden", False),
                    ],
                },
            ],
        },
    ]

    quizzes = []
    for qd in quiz_data:
        quiz = Quiz(
            title=qd["title"],
            category=qd["category"],
            duration_mins=qd["duration_mins"],
            total_points=qd["total_points"],
            scheduled_date=qd["scheduled_date"],
            scheduled_time=qd["scheduled_time"],
            status=QuizStatus.upcoming,
            creator_id=rohit.id,
        )
        db.add(quiz)
        db.flush()

        for order, q_data in enumerate(qd["questions"], start=1):
            question = Question(quiz_id=quiz.id, text=q_data["text"], order=order)
            db.add(question)
            db.flush()
            for opt_order, (opt_text, is_correct) in enumerate(q_data["options"], start=1):
                db.add(QuestionOption(
                    question_id=question.id,
                    text=opt_text,
                    is_correct=is_correct,
                    order=opt_order,
                ))
        quizzes.append(quiz)

    db.flush()

    # ── Historical completed attempts (for analytics) ─────────────────────────
    historical = [
        (QuizCategory.computer_science, 75, 14),
        (QuizCategory.mathematics,      80, 13),
        (QuizCategory.history,          72, 12),
        (QuizCategory.science,          78, 11),
        (QuizCategory.computer_science, 82, 10),
        (QuizCategory.mathematics,      79, 9),
        (QuizCategory.geography,        76, 8),
        (QuizCategory.history,          83, 7),
        (QuizCategory.science,          85, 6),
        (QuizCategory.computer_science, 88, 5),
        (QuizCategory.mathematics,      84, 4),
        (QuizCategory.computer_science, 100, 1),   # perfect score
    ]

    for cat, score_pct, days_ago in historical:
        hist_quiz = Quiz(
            title=f"{cat.value} Practice Quiz",
            category=cat,
            duration_mins=30,
            total_points=100,
            status=QuizStatus.completed,
            creator_id=rohit.id,
        )
        db.add(hist_quiz)
        db.flush()

        completed_dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        attempt = QuizAttempt(
            user_id=rohit.id,
            quiz_id=hist_quiz.id,
            score=score_pct,
            score_pct=float(score_pct),
            is_completed=True,
            started_at=completed_dt - timedelta(minutes=20),
            completed_at=completed_dt,
        )
        db.add(attempt)

    # ── Student enrollments ───────────────────────────────────────────────────
    for quiz in quizzes:
        for student in students:
            db.add(QuizAttempt(user_id=student.id, quiz_id=quiz.id))

    # ── Notifications ─────────────────────────────────────────────────────────
    db.add_all([
        Notification(
            user_id=rohit.id,
            type=NotificationType.system,
            title="Welcome to Curio! 🎉",
            message=f"Hi Rohit, your account is ready. Start by creating or taking a quiz!",
            is_read=False,
        ),
        Notification(
            user_id=rohit.id,
            type=NotificationType.achievement,
            title="🏆 Perfect Score!",
            message="You scored 100% in Computer Science Practice Quiz. Outstanding!",
            is_read=False,
        ),
        Notification(
            user_id=admin.id,
            type=NotificationType.system,
            title="Welcome to Curio! 🎉",
            message="Your admin account is set up.",
            is_read=False,
        ),
    ])

    db.commit()
    print("✅ Seeding complete!")
    print("\n  Demo accounts:")
    print("  ┌────────────────────────────────────────────────────────────────┐")
    print("  │  Admin   │ admin@projexi.com              │ admin1234          │")
    print("  │  Teacher │ rohitrk.singh1920@gmail.com    │ rohit1234          │")
    print("  │  Student │ alice@example.com              │ student123         │")
    print("  └────────────────────────────────────────────────────────────────┘")
    db.close()


if __name__ == "__main__":
    seed()
