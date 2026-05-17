# AI-Powered Personalized Health & Fitness Tracker

A Flask web application for personalized health tracking, diet and workout recommendations, habit logging, mental health journaling, gamification, and an AI health coach.

## Features

- Secure registration with email OTP verification
- Login, logout, forgot-password OTP reset, password hashing, session timeout, CSRF checks
- MongoDB Atlas persistence with Flask-PyMongo and PyMongo
- Multi-step health profile wizard
- BMI, BMR, TDEE, macro targets, diet recommendations, and workout recommendations
- Dashboard with habits, food logging, macro charts, mood trends, reminders, achievements, and dark mode
- Smart progress prediction for 7-day and 30-day expected weight trends
- Health risk indicators for obesity, diabetes, and heart health
- Personalized AI coach using profile, BMI, goals, logs, habits, and workout history

## MongoDB Collections

The app uses these collections:

`users`, `profiles`, `daily_logs`, `diet_logs`, `workouts`, `chat_history`, `habits`, `mood_logs`, `achievements`, `feedback`, `predictions`, `otp_verification`

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | HTML5, Bootstrap 5, Chart.js |
| Backend | Python 3.10+, Flask |
| Database | MongoDB Atlas via Flask-PyMongo and PyMongo |
| ML | scikit-learn |
| AI Coach | OpenAI API with rule-based fallback |

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env` from `.env.example`:

```env
SECRET_KEY=your-random-secret-key
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/health_tracker

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
SESSION_TIMEOUT_SECONDS=3600
```

Run the app:

```bash
python app.py
```

Open `http://localhost:5000`.

## Authentication Flow

Registration:

1. User submits name, email, password, and confirm password.
2. App validates input, hashes the password, creates a 6-digit OTP, and sends it by SMTP.
3. User verifies the OTP within 5 minutes.
4. Account is created in MongoDB and the user completes the profile wizard.

Forgot password:

1. User enters email.
2. App sends reset OTP.
3. User enters OTP and a new password.
4. Password hash is updated.

If SMTP is not configured, the development OTP is flashed so local testing is still possible.

## Project Structure

```text
health_tracker/
|-- app.py                 Main Flask application and routes
|-- db.py                  MongoDB initialization and document wrappers
|-- utils.py               OTP, SMTP, validation, and CSRF helpers
|-- config.py              Environment-based configuration
|-- health_calc.py         BMI, BMR, TDEE, macro calculations
|-- ml/                    Diet model and recommendation engine
|-- templates/             Auth, profile, dashboard, chatbot, recommendation pages
|-- static/css/style.css   Custom responsive UI and dark mode
|-- static/js/             Charts, chatbot, auth OTP, profile wizard scripts
|-- models/                Generated ML model artifacts
|-- requirements.txt
|-- .env.example
`-- README.md
```

## Notes

- Do not hardcode MongoDB or SMTP credentials. Keep them in `.env`.
- The AI coach works without an API key using a personalized rule-based fallback.
- MongoDB indexes are created on startup for users, profiles, logs, habits, chat history, and OTP expiry.

## Deployment (Render)

1. Push this repository to GitHub.
2. Create a new Web Service on Render and connect your GitHub repo.
3. Set the build command to `pip install -r requirements.txt` and the start command to `gunicorn app:app`.
4. Add the required environment variables in the Render dashboard:
	- `SECRET_KEY`
	- `MONGO_URI`
	- `MONGO_DBNAME` (optional)
	- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS`
	- `OPENAI_API_KEY` (optional)
	- `OPENAI_MODEL` (optional)
	- `SESSION_TIMEOUT_SECONDS` (optional)
5. Deploy and monitor logs for any startup errors (missing env variables, dataset/model training).

Render example (`render.yaml`) is included for an easy infra-as-code setup.
