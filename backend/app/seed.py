



from datetime import date, time, datetime, timedelta, timezone

from backend.app.core.database import SessionLocal, engine, Base
from backend.app.core.security import hash_password

from backend.app.models.user import User, UserRole
from backend.app.models.quiz import (
    Quiz, Question, QuestionOption,
    QuizStatus, QuizCategory, QuizEnrollment,
)
from backend.app.models.attempt import QuizAttempt, AttemptAnswer
from backend.app.models.notification import Notification, NotificationType


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        if db.query(User).count() > 0:
            print("Database already seeded. Skipping.")
            return

        print("Seeding database...")

        # ── Users ────────────────────────────────────────────────────────────
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
        student_data = [
            ("Alice Johnson",  "alice@example.com"),
            ("Bob Smith",      "bob@example.com"),
            ("Charlie Brown",  "charlie@example.com"),
            ("Diana Prince",   "diana@example.com"),
            ("Ethan Hunt",     "ethan@example.com"),
        ]
        students = [
            User(
                full_name=name,
                email=email,
                hashed_password=hash_password("student123"),
                role=UserRole.student,
            )
            for name, email in student_data
        ]

        db.add_all([admin, rohit] + students)
        db.flush()

        # ── Quizzes ───────────────────────────────────────────────────────────
        quiz_data = [
            {
                "title": "Advanced Python Concepts",
                "category": QuizCategory.computer_science,
                "duration_mins": 45,
                "total_points": 100,
                "scheduled_date": date(2026, 6, 20),
                "scheduled_time": time(10, 0),
                "status": QuizStatus.upcoming,
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
                "status": QuizStatus.upcoming,
                "questions": [
                    {
                        "text": "In which year did World War II begin?",
                        "options": [
                            ("1935", False), ("1939", True),
                            ("1941", False), ("1945", False),
                        ],
                    },
                    {
                        "text": "What was the code name for the Allied invasion of Normandy?",
                        "options": [
                            ("Operation Torch", False),
                            ("Operation Overlord", True),
                            ("Operation Barbarossa", False),
                            ("Operation Market Garden", False),
                        ],
                    },
                ],
            },
            {
                "title": "DSA Fundamentals",
                "category": QuizCategory.computer_science,
                "duration_mins": 30,
                "total_points": 100,
                "scheduled_date": None,
                "scheduled_time": None,
                "status": QuizStatus.active,
                "questions": [
                    {
                        "text": "What is the time complexity of binary search?",
                        "options": [
                            ("O(n)", False), ("O(log n)", True),
                            ("O(n log n)", False), ("O(1)", False),
                        ],
                    },
                    {
                        "text": "Which data structure uses LIFO order?",
                        "options": [
                            ("Queue", False), ("Stack", True),
                            ("Linked List", False), ("Heap", False),
                        ],
                    },
                ],
            },
            {
                "title": "Math Quiz",
                "category": QuizCategory.mathematics,
                "duration_mins": 20,
                "total_points": 50,
                "scheduled_date": None,
                "scheduled_time": None,
                "status": QuizStatus.active,
                "questions": [
                    {
                        "text": "What is the derivative of x²?",
                        "options": [
                            ("x", False), ("2x", True),
                            ("x²", False), ("2", False),
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
                status=qd["status"],
                creator_id=rohit.id,
            )
            db.add(quiz)
            db.flush()

            for order, q_data in enumerate(qd["questions"], start=1):
                question = Question(
                    quiz_id=quiz.id,
                    text=q_data["text"],
                    order=order,
                )
                db.add(question)
                db.flush()
                for opt_order, (opt_text, is_correct) in enumerate(
                    q_data["options"], start=1
                ):
                    db.add(QuestionOption(
                        question_id=question.id,
                        text=opt_text,
                        is_correct=is_correct,
                        order=opt_order,
                    ))
            quizzes.append(quiz)

        db.flush()

        # ── ENROLLMENT — students are assigned to quizzes ─────────────────────
        #
        # ROOT CAUSE FIX:
        # The old seed created bare QuizAttempt rows for students, which did NOT
        # create QuizEnrollment rows. Since list_quizzes now filters students by
        # QuizEnrollment (not QuizAttempt), students saw 0 quizzes.
        #
        # Fix: create QuizEnrollment rows + send notification to each student.
        #
        # Assignment matrix:
        #   Python quiz   → Alice, Bob, Charlie
        #   WWII quiz     → Alice, Bob, Diana, Ethan
        #   DSA quiz      → all students
        #   Math quiz     → Charlie, Diana, Ethan
        python_quiz, wwii_quiz, dsa_quiz, math_quiz = quizzes

        assignment_map = {
            python_quiz.id: [students[0], students[1], students[2]],       # Alice, Bob, Charlie
            wwii_quiz.id:   [students[0], students[1], students[3], students[4]],  # Alice, Bob, Diana, Ethan
            dsa_quiz.id:    students,                                        # all 5
            math_quiz.id:   [students[2], students[3], students[4]],        # Charlie, Diana, Ethan
        }

        for quiz_id, enrolled_students in assignment_map.items():
            quiz_obj = next(q for q in quizzes if q.id == quiz_id)
            for student in enrolled_students:
                db.add(QuizEnrollment(quiz_id=quiz_id, user_id=student.id))
                db.add(Notification(
                    user_id=student.id,
                    type=NotificationType.quiz_assigned,
                    title="New Quiz Assigned",
                    message=(
                        f"You have been enrolled in '{quiz_obj.title}' "
                        f"by {rohit.full_name}. Good luck!"
                    ),
                    is_read=False,
                ))

        db.flush()

        # ── Historical completed attempts (analytics data for Rohit) ──────────
        historical = [
            (QuizCategory.computer_science, 75, 14),
            (QuizCategory.mathematics,      80, 13),
            (QuizCategory.history,          72, 12),
            (QuizCategory.science,          78, 11),
            (QuizCategory.computer_science, 82, 10),
            (QuizCategory.mathematics,      79,  9),
            (QuizCategory.geography,        76,  8),
            (QuizCategory.history,          83,  7),
            (QuizCategory.science,          85,  6),
            (QuizCategory.computer_science, 88,  5),
            (QuizCategory.mathematics,      84,  4),
            (QuizCategory.computer_science, 100,  1),   # perfect score
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
            db.add(QuizAttempt(
                user_id=rohit.id,
                quiz_id=hist_quiz.id,
                score=float(score_pct),
                score_pct=float(score_pct),
                is_completed=True,
                started_at=completed_dt - timedelta(minutes=20),
                completed_at=completed_dt,
            ))

        # ── Notifications ─────────────────────────────────────────────────────
        db.add_all([
            Notification(
                user_id=rohit.id,
                type=NotificationType.system,
                title="Welcome to Curio!",
                message="Hi Rohit, your teacher account is ready. Create quizzes and assign students!",
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
                title="Welcome to Curio!",
                message="Your admin account is set up. Use the admin panel to manage users and roles.",
                is_read=False,
            ),
        ])

        db.commit()

        print("✅  Seeding complete!")
        print("\n  Demo accounts:")
        print("  ┌──────────────────────────────────────────────────────────────┐")
        print("  │  Admin   │ admin@projexi.com              │ admin1234        │")
        print("  │  Teacher │ rohitrk.singh1920@gmail.com    │ rohit1234        │")
        print("  │  Student │ alice@example.com              │ student123       │")
        print("  └──────────────────────────────────────────────────────────────┘")
        print("\n  Student quiz assignments:")
        print("  Alice  → Python, WWII, DSA")
        print("  Bob    → Python, WWII, DSA")
        print("  Charlie→ Python, DSA, Math")
        print("  Diana  → WWII, DSA, Math")
        print("  Ethan  → WWII, DSA, Math")

    except Exception as e:
        db.rollback()
        print(f"❌  Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
