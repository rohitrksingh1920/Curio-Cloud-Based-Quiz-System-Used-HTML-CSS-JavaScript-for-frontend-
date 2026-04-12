# Cloud Quiz — Production Deployment Guide
## FastAPI + PostgreSQL + AWS EC2 + Nginx

---

## 📁 Project Structure

```
cloud_quiz_production/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py        # Settings (reads .env)
│   │   │   ├── database.py      # PostgreSQL engine + session pool
│   │   │   └── security.py      # JWT + bcrypt helpers
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── routers/             # API route handlers
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── main.py              # FastAPI app + lifespan + middleware
│   │   └── seed.py              # Demo data seeder
│   ├── Dockerfile
│   ├── requirements.txt         # Includes psycopg2-binary
│   └── .env.example
├── frontend/                    # HTML/CSS/JS (served by Nginx)
│   ├── api.js                   # Relative-URL API client (works on any host)
│   ├── index.html               # Login
│   ├── signup.html
│   ├── dashboard.html
│   ├── create-quiz.html
│   ├── my-quizzes.html
│   ├── analytics.html
│   ├── settings.html
│   ├── notifications.html
│   ├── take-quiz.html
│   └── style.css
├── nginx/
│   ├── cloudquiz.conf           # Docker Compose (upstream: backend:8000)
│   └── cloudquiz-ec2.conf       # EC2 bare-metal (upstream: 127.0.0.1:8000)
├── alembic/
│   └── env.py                   # Alembic migration environment
├── alembic.ini
├── docker-compose.yml           # Local dev with PostgreSQL + Nginx
└── scripts/
    ├── deploy.sh                # Full EC2 bootstrap (run once)
    ├── update.sh                # Rolling update (run on every re-deploy)
    ├── backup.sh                # PostgreSQL backup
    └── cloudquiz.service        # Systemd unit file
```

---

## 🗺️ Architecture

```
Internet
    │
    ▼
[EC2 Security Group — port 80, 22]
    │
    ▼
Nginx :80
    ├── /api/*   → proxy → Gunicorn :8000 → FastAPI → PostgreSQL
    ├── /health  → proxy → Gunicorn :8000
    └── /*       → static → /home/ubuntu/cloud_quiz/frontend/
```

---

## 🚀 Option A — AWS EC2 Deployment (Production)

### Step 1: Launch EC2 Instance

1. Open **AWS Console → EC2 → Launch Instance**
2. Settings:
   - **Name**: `cloud-quiz-server`
   - **AMI**: `Ubuntu Server 22.04 LTS` (Free Tier eligible)
   - **Instance type**: `t3.micro` (Free Tier) or `t3.small` for better performance
   - **Key pair**: Create new → download `.pem` file → keep it safe
   - **Security Group** — Add these inbound rules:

| Type  | Protocol | Port | Source    |
|-------|----------|------|-----------|
| SSH   | TCP      | 22   | My IP     |
| HTTP  | TCP      | 80   | 0.0.0.0/0 |
| HTTPS | TCP      | 443  | 0.0.0.0/0 |

3. **Storage**: 20 GB gp3 (minimum)
4. Click **Launch Instance**
5. Note your **EC2 Public IP** from the console

---

### Step 2: Connect to EC2

```bash
# Fix permissions on your key file
chmod 400 ~/Downloads/your-key.pem

# SSH into the instance
ssh -i ~/Downloads/your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

---

### Step 3: Upload Project Files

From your **local machine** (new terminal tab):

```bash
# Zip the project
zip -r cloud_quiz.zip cloud_quiz_production/ -x "*.pyc" -x "*/__pycache__/*"

# Upload to EC2
scp -i ~/Downloads/your-key.pem cloud_quiz.zip ubuntu@YOUR_EC2_PUBLIC_IP:~/

# Back on EC2 — unzip
unzip ~/cloud_quiz.zip
mv cloud_quiz_production ~/cloud_quiz
```

---

### Step 4: Run the Deploy Script

```bash
cd ~/cloud_quiz
chmod +x scripts/deploy.sh scripts/update.sh scripts/backup.sh
./scripts/deploy.sh
```

The script automatically:
- Installs Python 3.11, PostgreSQL 15, Nginx
- Creates the database and user with a generated password
- Creates a Python virtualenv and installs all dependencies
- Writes `.env` with generated `SECRET_KEY` and `DATABASE_URL`
- Runs Alembic migrations to create all tables
- Seeds demo data
- Configures Nginx as reverse proxy
- Installs and starts the systemd service

**Total time: ~5–8 minutes**

---

### Step 5: Verify Deployment

```bash
# Check application status
sudo systemctl status cloudquiz

# Check Nginx status
sudo systemctl status nginx

# Test health endpoint
curl http://localhost/health

# View live logs
sudo journalctl -u cloudquiz -f
```

Open your browser: **http://YOUR_EC2_PUBLIC_IP**

---

### Step 6: Configure .env (after deploy)

The deploy script auto-generates `.env`. To view or edit it:

```bash
cat ~/cloud_quiz/backend/.env
nano ~/cloud_quiz/backend/.env

# After any .env change, restart the service
sudo systemctl restart cloudquiz
```

---

## 🐳 Option B — Local Development with Docker Compose

### Prerequisites
- Docker Desktop installed

### Start

```bash
cd cloud_quiz_production
docker compose up --build
```

This starts:
- PostgreSQL on port 5432
- FastAPI backend on port 8000 (with hot-reload)
- Nginx on port 80 serving frontend + proxying API

Open **http://localhost** in your browser.

### Stop

```bash
docker compose down          # stop containers
docker compose down -v       # stop + wipe database
```

### View logs

```bash
docker compose logs -f backend    # FastAPI logs
docker compose logs -f nginx      # Nginx logs
docker compose logs -f db         # PostgreSQL logs
```

---

## 🗄️ Database (PostgreSQL)

### Connection details (after deploy)
```
Host:     localhost (on EC2)
Port:     5432
Database: cloudquiz
User:     cloudquiz
Password: (auto-generated, stored in .env)
```

### Run migrations manually
```bash
cd ~/cloud_quiz/backend
source ../venv/bin/activate
alembic -c ../alembic.ini upgrade head
```

### Generate a new migration (after model changes)
```bash
alembic -c ../alembic.ini revision --autogenerate -m "describe_your_change"
alembic -c ../alembic.ini upgrade head
```

### Rollback last migration
```bash
alembic -c ../alembic.ini downgrade -1
```

### Connect with psql
```bash
sudo -u postgres psql -d cloudquiz
# or
psql postgresql://cloudquiz:PASSWORD@localhost:5432/cloudquiz
```

### Useful psql queries
```sql
-- List all tables
\dt

-- Count users
SELECT count(*) FROM users;

-- See all quizzes
SELECT id, title, status, creator_id FROM quizzes;

-- Check attempts
SELECT u.full_name, q.title, a.score_pct, a.is_completed
FROM quiz_attempts a
JOIN users u ON u.id = a.user_id
JOIN quizzes q ON q.id = a.quiz_id;
```

---

## 🔄 Updating the Application

Every time you push new code:

```bash
# Upload new files to EC2
scp -i ~/Downloads/your-key.pem -r ./backend ubuntu@YOUR_EC2_PUBLIC_IP:~/cloud_quiz/
scp -i ~/Downloads/your-key.pem -r ./frontend ubuntu@YOUR_EC2_PUBLIC_IP:~/cloud_quiz/

# SSH in and run the update script
ssh -i ~/Downloads/your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
~/cloud_quiz/scripts/update.sh
```

Or with git:
```bash
# On EC2 (if you push to GitHub)
cd ~/cloud_quiz && git pull origin main
~/cloud_quiz/scripts/update.sh
```

---

## 💾 Backups

### Run a manual backup
```bash
~/cloud_quiz/scripts/backup.sh
```

### Schedule automatic daily backups (2 AM)
```bash
crontab -e
# Add this line:
0 2 * * * /home/ubuntu/cloud_quiz/scripts/backup.sh >> /var/log/cloudquiz/backup.log 2>&1
```

### Restore from backup
```bash
# Decompress
gunzip ~/cloud_quiz/backups/cloudquiz_20260325_020000.sql.gz

# Restore
psql postgresql://cloudquiz:PASSWORD@localhost:5432/cloudquiz \
    < ~/cloud_quiz/backups/cloudquiz_20260325_020000.sql
```

---

## 🔑 Demo Accounts (after seeding)

| Role    | Email                | Password    |
|---------|----------------------|-------------|
| Admin   | admin@projexi.com    | admin1234   |
| Teacher | piyush@example.com   | piyush1234  |
| Student | alice@example.com    | student123  |

---

## 📡 API Reference

| Method | Endpoint                                | Auth | Description                   |
|--------|-----------------------------------------|------|-------------------------------|
| POST   | /api/auth/signup                        | ❌   | Register new account          |
| POST   | /api/auth/login                         | ❌   | Login, get JWT token          |
| GET    | /api/auth/me                            | ✅   | Get current user              |
| GET    | /api/dashboard/stats                    | ✅   | Total quizzes/participants/avg|
| GET    | /api/dashboard/upcoming-quizzes         | ✅   | Upcoming quiz cards           |
| GET    | /api/quizzes                            | ✅   | List my quizzes (filterable)  |
| POST   | /api/quizzes                            | ✅   | Create quiz with questions    |
| GET    | /api/quizzes/{id}                       | ✅   | Get full quiz detail          |
| PATCH  | /api/quizzes/{id}                       | ✅   | Update quiz metadata          |
| DELETE | /api/quizzes/{id}                       | ✅   | Delete quiz                   |
| GET    | /api/quizzes/{id}/take                  | ✅   | Take quiz (no correct answers)|
| POST   | /api/quizzes/{id}/submit                | ✅   | Submit answers, get score     |
| GET    | /api/analytics                          | ✅   | Score trend + subject data    |
| GET    | /api/settings/profile                   | ✅   | Get profile + preferences     |
| PATCH  | /api/settings/profile                   | ✅   | Update profile/dark mode/lang |
| POST   | /api/settings/security/change-password  | ✅   | Change password               |
| PATCH  | /api/settings/notifications             | ✅   | Toggle email/push prefs       |
| GET    | /api/notifications                      | ✅   | List notifications            |
| PATCH  | /api/notifications/{id}/read            | ✅   | Mark one as read              |
| POST   | /api/notifications/mark-all-read        | ✅   | Mark all as read              |
| DELETE | /api/notifications/{id}                 | ✅   | Delete notification           |
| GET    | /health                                 | ❌   | Health check                  |

> **Swagger UI** is available at `http://YOUR_EC2_PUBLIC_IP/docs` when `DEBUG=true`

---

## 🛠️ Useful Commands (EC2)

```bash
# Application
sudo systemctl status  cloudquiz        # Check if running
sudo systemctl start   cloudquiz        # Start
sudo systemctl stop    cloudquiz        # Stop
sudo systemctl restart cloudquiz        # Hard restart
sudo systemctl reload  cloudquiz        # Graceful reload (zero-downtime)

# Logs
sudo journalctl -u cloudquiz -f         # Live application logs
sudo journalctl -u cloudquiz -n 100     # Last 100 lines
sudo tail -f /var/log/nginx/cloudquiz_error.log    # Nginx errors
sudo tail -f /var/log/nginx/cloudquiz_access.log   # Nginx access
sudo tail -f /var/log/cloudquiz/error.log          # Gunicorn errors

# Nginx
sudo nginx -t                           # Test config syntax
sudo systemctl reload nginx             # Reload config

# PostgreSQL
sudo systemctl status postgresql        # DB status
sudo -u postgres psql -d cloudquiz      # Connect to DB

# Python / venv
source ~/cloud_quiz/venv/bin/activate
python -m app.seed                      # Re-run seeder
alembic -c ../alembic.ini upgrade head  # Apply migrations

# Disk usage
df -h                                   # Disk space
du -sh ~/cloud_quiz/backups/            # Backup folder size
```

---

## ❌ Troubleshooting

### "502 Bad Gateway"
```bash
# Gunicorn is down — check logs
sudo journalctl -u cloudquiz -n 50
sudo systemctl restart cloudquiz
```

### "psycopg2.OperationalError: could not connect to server"
```bash
# PostgreSQL is down
sudo systemctl status postgresql
sudo systemctl start postgresql
# Check DATABASE_URL in .env is correct
cat ~/cloud_quiz/backend/.env | grep DATABASE_URL
```

### "relation does not exist" (missing tables)
```bash
# Migrations haven't run
cd ~/cloud_quiz/backend
source ../venv/bin/activate
alembic -c ../alembic.ini upgrade head
```

### "401 Unauthorized" on all API calls
```bash
# JWT SECRET_KEY may have changed — users must log in again
# This is expected after rotating secrets
```

### Port 80 already in use
```bash
sudo lsof -i :80
sudo systemctl stop apache2   # if Apache is running
sudo systemctl restart nginx
```

### Nginx config test fails
```bash
sudo nginx -t    # shows exact error line
sudo nginx -T    # prints full merged config
```

---

## 🔒 Production Hardening Checklist

- [ ] **Change SECRET_KEY** — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] **Set DEBUG=false** in `.env` — hides `/docs` and `/redoc`
- [ ] **Restrict FRONTEND_ORIGINS** — set to your exact domain/IP only
- [ ] **Set up SSL/HTTPS** — use Certbot + Let's Encrypt:
  ```bash
  sudo apt install certbot python3-certbot-nginx
  sudo certbot --nginx -d yourdomain.com
  ```
- [ ] **Set up daily backups** — add cron entry (see Backups section)
- [ ] **Restrict SSH** — in Security Group, change SSH source from `0.0.0.0/0` to your IP only
- [ ] **Enable UFW firewall**:
  ```bash
  sudo ufw allow 22/tcp
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw enable
  ```
- [ ] **Set up CloudWatch** — for EC2 metrics and alarms
- [ ] **Use RDS** — for managed PostgreSQL with automatic backups (recommended for production)

---

## 🔁 Moving to Amazon RDS (Optional)

To use RDS instead of the local PostgreSQL:

1. Create RDS PostgreSQL 15 instance in AWS Console
2. Note the **endpoint**, **username**, **password**, **database name**
3. Update `.env`:
   ```
   DATABASE_URL=postgresql://USER:PASSWORD@your-rds-endpoint.amazonaws.com:5432/cloudquiz
   ```
4. Make sure your EC2 Security Group allows outbound traffic to RDS on port 5432
5. Run migrations: `alembic -c ../alembic.ini upgrade head`
6. Restart: `sudo systemctl restart cloudquiz`
