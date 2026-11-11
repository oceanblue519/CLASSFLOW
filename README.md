# Classflow EMS

A role-based school platform built with React/TypeScript, FastAPI and SQLAlchemy. Local mode uses SQLite; set DATABASE_URL for PostgreSQL.

## Architecture

```mermaid
erDiagram
 USER ||--o| STUDENT_PROFILE : has
 USER ||--o| TEACHER_PROFILE : has
 USER ||--o{ CLASS : teaches
 CLASS ||--o{ ENROLLMENT : includes
 USER ||--o{ ENROLLMENT : joins
 CLASS ||--o{ ASSIGNMENT : publishes
 ASSIGNMENT ||--o{ SUBMISSION : receives
 CLASS ||--o{ QUIZ : offers
 QUIZ ||--o{ QUIZ_ATTEMPT : records
 CLASS ||--o{ ATTENDANCE : tracks
 USER ||--o{ NOTIFICATION : receives
```

`backend/app`: API, auth, persistence. `frontend/src`: client. `backend/schema.sql` documents the relational schema. Database changes are versioned through Alembic. Sessions use signed HttpOnly cookies, passwords use PBKDF2-SHA256, and class access is enforced by the API.

## Run on Windows 11

PowerShell terminal 1:
```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```
PowerShell terminal 2:
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. API docs: http://localhost:8000/docs. To bootstrap an admin, set ADMIN_EMAIL in backend/.env then register with that address. Teachers need admin approval. Run `alembic upgrade head` after configuring the database and after each new migration. PostgreSQL example: `postgresql+psycopg://user:password@localhost:5432/classflow`.

Google and Facebook sign-in are optional. Add each provider's client ID and secret to `backend/.env`, and register the matching callback URI shown by `GOOGLE_AUTH_REDIRECT_URI` or `FACEBOOK_AUTH_REDIRECT_URI` in that provider's developer console. OAuth-created accounts use the student role; teacher accounts still require administrator approval. Social sign-in stays disabled until the matching credentials are configured.

### Install Classflow for testing

The frontend is an installable Progressive Web App (PWA). Run the backend and frontend as above, open `http://localhost:5173` in Microsoft Edge or Chrome, then use the install icon in the address bar or the browser menu's **Install Classflow** option. The installed app opens in its own window. After the first online load, the app shell and static assets are cached; sign-in, classes, messaging, and other API-backed features still require the backend and a network connection.

On Android, open the deployed HTTPS site in Chrome and choose **Install app** or **Add to Home screen** from the browser menu. On iPhone/iPad, open it in Safari, tap **Share**, then **Add to Home Screen**. Phone installation and camera/microphone access require HTTPS; a computer's plain-HTTP LAN address is not a secure origin. Use a trusted HTTPS development setup or an HTTPS deployment when testing on a phone.

### Build native Windows and Android installers

These packages include the Classflow interface, but not the backend. Deploy the backend at an address reachable by each device before signing in. In the app, enter that API server address on the sign-in screen (for example, `https://school.example.com`). Android cannot use a computer's `localhost` address to reach that computer. For a hosted backend, configure `COOKIE_SECURE=true`, `SESSION_SAME_SITE=none`, and include the app origins in `CORS_ORIGINS` (at minimum `https://localhost` for Android and `http://127.0.0.1:4174` for Windows).

**Windows EXE:** From `frontend`, run `npm install` and `npm run app:windows`. The NSIS installer is written to `frontend/release/Classflow Setup 1.0.0.exe`. Run it to install Classflow. The installer is currently unsigned, so Windows may show a SmartScreen warning.

**Android APK:** Install Android Studio with Android SDK Platform 36 and JDK 21 or later. From `frontend`, run `npm install` and `npm run app:android:apk`. The debug APK is written to `frontend/android/app/build/outputs/apk/debug/app-debug.apk`; transfer it to the Android device and allow installation from that file source when prompted. This debug APK is for testing, not Play Store distribution.

### Phone and QR attendance

The interface adapts to phone screens and includes a horizontally scrolling bottom navigation. For same-network phone access during development, run Vite with `npm run dev -- --host 0.0.0.0` and open `http://<your-computer-LAN-IP>:5173` on the phone. Mobile browsers require a secure HTTPS origin for camera and microphone access. Teachers can use QR attendance or start a native audio/video classroom. The classroom records each participant join, leave, and connected duration; it does not record or store the call video/audio.

### Container deployment

Install Docker Desktop, copy `.env.example` to `.env` at the project root, and set unique values for `SECRET_KEY` and `POSTGRES_PASSWORD`. For example, generate each with `python -c "import secrets; print(secrets.token_hex(32))"`. Then run:

```powershell
docker compose up --build -d
```

Open `http://localhost:8080`. Compose starts PostgreSQL, runs Alembic migrations before the API, persists database data and uploads in named volumes, and serves the built frontend through Nginx. Set `ADMIN_EMAIL` before registering the matching account. For a public deployment, put a TLS reverse proxy in front, set `HTTP_PORT` as needed, set `FRONTEND_ORIGIN` to the public HTTPS origin, and set `COOKIE_SECURE=true`. Keep `.env` private and back up the database and uploads volumes. Do not expose the database port publicly.

The Compose file is a single-host deployment baseline. It does not provision TLS certificates, managed backups, malware scanning, object storage, a distributed rate limiter, or a secrets manager. Configure these at the hosting layer before storing real student records.

### Temporary Render preview

The root `render.yaml` provisions a free Render web service and PostgreSQL database for a temporary client preview. It builds the frontend into the API container, so the website and `/api` share one HTTPS origin. To deploy, push this project to a Git provider, create a Render Blueprint from the repository, and deploy it. Render's free web service can sleep while idle, and its free PostgreSQL database expires after 30 days; this setup is not for real student records or production. Configure `ADMIN_EMAIL` in the Render service environment before registering the administrator account. The preview keeps sign-in sessions for 30 days unless the user signs out; set `SESSION_MAX_AGE_SECONDS` to adjust this. For the Android app, enter the deployed HTTPS origin in its server-address panel.

Email verification and password recovery need SMTP credentials; delivery is disabled unless configured. Attendance exports are provided as CSV, Excel and PDF. Uploads use type and signature checks, with a configurable size limit; they are not antivirus scanned.

### Native virtual classroom

The Virtual Classroom uses in-app browser audio/video with no Google Meet account or connection. A teacher starts a live room from a class and enrolled students join from the session list. Participants can mute, turn off their camera, and leave; the teacher can end the room for everyone. Each join creates a separate attendance entry with join time, leave time, and time connected. If a browser closes unexpectedly, a heartbeat records the disconnect after a short timeout. The app records attendance metadata only, not classroom audio or video. Camera and microphone access on phones requires HTTPS; local `localhost` development is treated as secure by desktop browsers, but a phone connecting over the computer's LAN IP needs HTTPS.

## Implemented in this initial build

Implemented workflows include registration/login and account recovery, profile editing, student/teacher/admin roles, teacher approval and account suspension, class creation and join codes, activities, assignments/submissions/grading, private class messages, multiple-choice quizzes, teacher-confirmed attendance and exports, announcements, course materials, notifications, and native browser-based virtual classrooms with join/leave attendance records. Set SMTP credentials to enable email verification and account recovery.

This is a functional school-workspace starter, not a production-certified institutional platform. The current implementation does not include public marketing pages, profile photos, group project coordination, report cards, a personal planner/calendar, advanced analytics, certificates, two-factor authentication, scheduled/editable announcements, richer quiz question types, push/reminder delivery, attendance filtering/edit history, malware scanning, or managed object storage. Institutional privacy/legal review, accessibility review, load/security testing, and production operations configuration remain necessary before handling real student records. Run backend checks with `cd backend; .venv\\Scripts\\python.exe -m pytest` and build the frontend with `cd frontend; npm run build`.
