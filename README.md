# 📘 Curio — Cloud-Based Quiz System

A full-stack **cloud-based quiz platform** that enables **teachers to create quizzes**, **students to attempt them**, and **admins to manage the system**, with real-time analytics, leaderboard tracking, and notification support.

---

## 🚀 Features

### 👤 Authentication & Security

* JWT-based authentication system
* Role-based access control (**Admin / Teacher / Student**)
* Secure password hashing using bcrypt
* OTP-based password reset via email

---

### 🧑‍🏫 Teacher Features

* Create, update, and delete quizzes
* Add multiple questions with options
* Assign quizzes to specific students
* View dashboard statistics (participants, performance)

---

### 🎓 Student Features

* Access only assigned quizzes (enrollment-based system)
* Attempt quizzes with structured UI
* Submit answers and receive scores
* Track performance and analytics

---

### 🏆 Leaderboard System

* Ranking based on:

  * Highest score percentage
  * Earliest submission time
* Per-quiz leaderboard tracking

---

### 🔔 Notifications System

* Quiz assignment alerts
* System notifications and updates
* Mark as read / delete functionality

---

### 📊 Analytics Dashboard

* Average score tracking
* Pass rate calculation
* Score trend visualization
* Subject-wise performance analysis

---

### ⚙️ Admin Features

* Manage all users
* Change roles (student ↔ teacher ↔ admin)
* Activate / deactivate accounts
* Monitor system usage

---

### 🎨 UI Features

* Modern responsive UI
* Clean dashboard design
* Dark mode support
* Multiple pages (dashboard, analytics, quizzes, leaderboard)

---

## 🏗️ Tech Stack

### 🔹 Backend

* FastAPI
* SQLAlchemy
* PostgreSQL
* Alembic

### 🔹 Frontend

* HTML5
* CSS3
* Vanilla JavaScript

### 🔹 DevOps / Infrastructure

* Docker & Docker Compose
* Nginx (reverse proxy)
* Uvicorn + Gunicorn

---

## 📁 Project Structure

```
curio/
│
├── backend/
│   ├── app/
│   │   ├── core/        # config, security, database
│   │   ├── models/      # database models
│   │   ├── routers/     # API endpoints
│   │   ├── schemas/     # data validation
│   │
│   ├── main.py          # FastAPI entry point
│   ├── seed.py          # database seed script
│
├── frontend/
│   ├── HTML pages
│   ├── CSS styles
│   ├── JavaScript files
│
├── docker-compose.yml
├── nginx.conf
├── requirements.txt
└── README.md
```

---

## ⚙️ Installation & Setup

### 🔹 1. Clone Repository

```bash
git clone https://github.com/your-username/curio-quiz-system.git
cd curio-quiz-system
```

---

### 🔹 2. Setup Environment Variables

Create a `.env` file in the backend:

```env
DATABASE_URL=postgresql://postgres:1234@localhost:5432/curio_db
SECRET_KEY=your_secret_key
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
```

---

### 🔹 3. Run with Docker (Recommended)

```bash
docker-compose up --build
```

---

### 🔹 4. Run Locally (Without Docker)

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

---

## 🌐 API Documentation

* Swagger UI → http://localhost:8000/docs
* ReDoc → http://localhost:8000/redoc

---

## 🧪 Seed Database

```bash
python backend/seed.py
```

This will create:

* Admin account
* Teacher account
* Sample students
* Demo quizzes

---

## 🔐 Default Credentials

| Role    | Email                                         | Password   |
| ------- | --------------------------------------------- | ---------- |
| Admin   | [admin@projexi.com](mailto:admin@projexi.com) | admin1234  |
| Teacher | rohitrk.singh...                              | rohit1234  |
| Student | [alice@example.com](mailto:alice@example.com) | student123 |

---

## 📡 Key API Endpoints

### Auth

* `POST /api/auth/signup`
* `POST /api/auth/login`
* `POST /api/auth/forgot-password`

### Quiz

* `GET /api/quizzes`
* `POST /api/quizzes`
* `GET /api/quizzes/{id}/take`
* `POST /api/quizzes/{id}/submit`

### Dashboard

* `GET /api/dashboard/stats`

### Leaderboard

* `GET /api/leaderboard/{quiz_id}`

---

## 📸 Screenshots

*Add screenshots here to showcase UI (recommended for GitHub projects)*

---

## 🔮 Future Improvements

* Redis-based OTP storage
* Real-time quiz updates (WebSockets)
* AI-based question generation
* Mobile app version
* Enhanced multi-language support

---

## 🤝 Contributing

Contributions are welcome!
Feel free to fork the repository and submit a pull request.

---

## 📄 License

This project is licensed under the MIT License.

---

## 👨‍💻 Author

**Rohit Singh**

---

## ⭐ Final Note

This project demonstrates:

* Full-stack development
* Scalable backend architecture
* Role-based system design
* Real-world application structure

If you found this project helpful, consider giving it a ⭐
