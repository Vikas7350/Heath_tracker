"""
AI-Powered Personalized Health & Fitness Tracker
Flask application using MongoDB Atlas for persistence.
"""
import json
from datetime import date, datetime, timedelta

import numpy as np
from openai import OpenAI
from sklearn.linear_model import LinearRegression
from pymongo.errors import DuplicateKeyError, PyMongoError
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_login import (LoginManager, current_user, login_required,
                         login_user, logout_user)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from db import as_dict, doc, init_db, mongo, now_utc, oid, user_doc, safe_find_one, safe_insert_one, safe_update_one, safe_delete_many
from validators import validate_registration, validate_login, validate_profile
from health_calc import full_health_report
from ml.recommender import get_diet_plan, get_workout_plan
from utils import (can_request_otp, csrf_token, generate_otp, save_otp,
                   send_otp_email, send_otp_email_async, valid_email, validate_csrf, verify_otp, to_int, to_float)


app = Flask(__name__)
app.config.from_object(Config)
init_db(app)

app.jinja_env.globals.update(enumerate=enumerate, csrf_token=csrf_token)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"


@app.errorhandler(PyMongoError)
def handle_mongo_error(error):
    app.logger.warning("MongoDB operation failed: %s", error)
    session.pop("_user_id", None)
    session.pop("_fresh", None)
    flash("Database connection is temporarily unavailable. Please check MongoDB Atlas/network access and try again.", "danger")
    return redirect(url_for("login"))


@app.before_request
def harden_session_and_csrf():
    session.permanent = True
    if request.method == "POST":
        token = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
        if not validate_csrf(token):
            abort(400, description="Invalid CSRF token.")


@login_manager.user_loader
def load_user(uid):
    user_id = oid(uid)
    if not user_id:
        return None
    try:
        user_data = mongo.db.users.find_one({"_id": user_id})
        return user_doc(user_data)
    except PyMongoError as e:
        app.logger.warning("Failed to load user from DB: %s", e)
        session.pop("_user_id", None)
        session.pop("_fresh", None)
        return None
    except Exception as e:
        app.logger.warning("Unexpected error loading user: %s", e)
        session.pop("_user_id", None)
        session.pop("_fresh", None)
        return None


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if "otp_code" in request.form or "otp_digit" in request.form:
            flash("Please verify your OTP on this page.", "info")
            return redirect(url_for("verify_otp_route"))
        try:
            ok, errors = validate_registration(request.form)
            if not ok:
                for v in errors.values():
                    flash(v, "danger")
                return render_template("auth/register.html")

            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            existing = safe_find_one('users', {"email": email})
            if existing:
                flash("Email already exists. Please log in.", "warning")
                return redirect(url_for("login"))

            pending = safe_find_one('pending_users', {"email": email})
            if pending and pending.get("created_at") and seconds_since(pending["created_at"]) < 60:
                flash("Please wait a minute before requesting another OTP.", "warning")
                return render_template("auth/register.html")

            otp = generate_otp()
            app.logger.debug("OTP generated for registration: %s", otp)
            safe_update_one('pending_users', {"email": email}, {"$set": {
                "name": name,
                "email": email,
                "password_hash": generate_password_hash(password),
                "otp": otp,
                "expires_at": now_utc() + timedelta(minutes=5),
                "created_at": now_utc(),
            }}, upsert=True)
            session["pending_registration_email"] = email
            session.pop("pending_registration", None)
            
            # Check if SMTP is configured
            mail_configured = (app.config.get("MAIL_SERVER") and 
                             app.config.get("MAIL_USERNAME") and 
                             app.config.get("MAIL_PASSWORD"))
            
            if mail_configured:
                # Send email in background thread (non-blocking)
                send_otp_email_async(email, otp, "account verification")
                flash("OTP sent to your email. It expires in 5 minutes.", "success")
            else:
                # Development mode - show OTP on screen
                flash(f"SMTP is not configured. Development OTP: {otp}", "info")
            
            return redirect(url_for("verify_otp_route"))
        except PyMongoError as e:
            app.logger.exception("Registration DB error: %s", e)
            flash("Could not start registration. Please check the database connection and try again.", "danger")
            return render_template("auth/register.html")
        except Exception as e:
            app.logger.exception("Registration error: %s", e)
            flash("Something went wrong. Please try again.", "danger")
            return render_template("auth/register.html")
    return render_template("auth/register.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp_route():
    email = (session.get("pending_registration_email") or request.args.get("email", "")).strip().lower()
    pending = safe_find_one('pending_users', {"email": email}) if email else None
    if not pending:
        flash("Start registration first.", "info")
        return redirect(url_for("register"))
    if request.method == "POST":
        try:
            user_otp = normalize_otp(request.form)
            app.logger.debug("OTP entered during verification: %s", user_otp)
            if pending.get("expires_at") and pending["expires_at"].replace(tzinfo=now_utc().tzinfo) <= now_utc():
                flash("OTP expired. Please resend OTP.", "danger")
                return render_template("auth/verify_otp.html", email=email, purpose="register")
            if user_otp != str(pending.get("otp", "")).strip():
                flash("Invalid OTP.", "danger")
                return render_template("auth/verify_otp.html", email=email, purpose="register")
            if safe_find_one('users', {"email": email}):
                safe_delete_many('pending_users', {"email": email})
                session.pop("pending_registration_email", None)
                flash("Email already exists. Please log in.", "warning")
                return redirect(url_for("login"))

            result = safe_insert_one('users', {
                "name": pending["name"],
                "email": pending["email"],
                "password_hash": pending["password_hash"],
                "is_verified": True,
                "xp": 0,
                "streak": 0,
                "last_activity_date": None,
                "badges": [],
                "created_at": now_utc(),
            })
            safe_delete_many('pending_users', {"email": email})
            session.pop("pending_registration_email", None)
            user = user_doc(safe_find_one('users', {"_id": result.inserted_id})) if result else None
            login_user(user)
            app.logger.info("OTP verified and user logged in: %s", user.email if user else 'unknown')
            flash("Account verified! Complete your health profile.", "success")
            return redirect(url_for("setup_profile"))
        except DuplicateKeyError as e:
            app.logger.warning("OTP verification duplicate error: %s", e)
            mongo.db.pending_users.delete_many({"email": email})
            session.pop("pending_registration_email", None)
            flash("Email already exists. Please log in.", "warning")
            return redirect(url_for("login"))
        except Exception as e:
            app.logger.exception("OTP verification error: %s", e)
            flash("Could not verify OTP. Please try again.", "danger")
            return render_template("auth/verify_otp.html", email=email, purpose="register")
    return render_template("auth/verify_otp.html", email=email, purpose="register")


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    purpose = request.form.get("purpose", "register")
    email = None
    if purpose == "reset":
        email = session.get("reset_email")
    else:
        email = session.get("pending_registration_email")
    if not email:
        flash("No OTP request is active.", "warning")
        return redirect(url_for("login"))
    try:
        otp = generate_otp()
        app.logger.debug("OTP generated for resend: %s", otp)
        if purpose == "register":
            pending = mongo.db.pending_users.find_one({"email": email})
            if not pending:
                flash("Start registration first.", "info")
                return redirect(url_for("register"))
            if pending.get("created_at") and seconds_since(pending["created_at"]) < 60:
                flash("Please wait a minute before requesting another OTP.", "warning")
                return redirect(url_for("verify_otp_route"))
            mongo.db.pending_users.update_one(
                {"email": email},
                {"$set": {"otp": otp, "expires_at": now_utc() + timedelta(minutes=5), "created_at": now_utc()}},
            )
        else:
            if not can_request_otp(email, purpose):
                flash("Please wait a minute before requesting another OTP.", "warning")
                return redirect(url_for("reset_password"))
            save_otp(email, purpose, otp)
        
        # Check if SMTP is configured
        mail_configured = (app.config.get("MAIL_SERVER") and 
                         app.config.get("MAIL_USERNAME") and 
                         app.config.get("MAIL_PASSWORD"))
        
        if mail_configured:
            send_otp_email_async(email, otp, "password reset" if purpose == "reset" else "account verification")
            flash("A new OTP was sent.", "info")
        else:
            flash(f"SMTP is not configured. Development OTP: {otp}", "info")
    except Exception as e:
        app.logger.exception("Resend OTP error: %s", e)
        flash("Could not resend OTP. Please try again.", "danger")
    return redirect(url_for("verify_otp_route") if purpose == "register" else url_for("reset_password"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        ok, errors = validate_login(request.form)
        if not ok:
            for v in errors.values():
                flash(v, "danger")
            return render_template("auth/login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = safe_find_one('users', {"email": email, "is_verified": True})
        if user and check_password_hash(user.get("password_hash", ""), password):
            login_user(user_doc(user))
            nxt = request.args.get("next")
            return redirect(nxt or url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("auth/login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = mongo.db.users.find_one({"email": email})
        if not user:
            flash("If that email exists, an OTP has been sent.", "info")
            return redirect(url_for("login"))
        if not can_request_otp(email, "reset"):
            flash("Please wait a minute before requesting another OTP.", "warning")
            return render_template("auth/forgot_password.html")
        otp = generate_otp()
        save_otp(email, "reset", otp)
        session["reset_email"] = email
        sent = send_otp_email(email, otp, "password reset")
        flash("Password reset OTP sent." if sent else f"SMTP is not configured. Development OTP: {otp}", "info")
        return redirect(url_for("reset_password"))
    return render_template("auth/forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = session.get("reset_email")
    if not email:
        flash("Enter your email to reset your password.", "info")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        otp = normalize_otp(request.form)
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 6 or password != confirm:
            flash("Passwords must match and be at least 6 characters.", "danger")
            return render_template("auth/reset_password.html", email=email)
        if not verify_otp(email, "reset", otp):
            flash("Invalid or expired OTP.", "danger")
            return render_template("auth/reset_password.html", email=email)
        mongo.db.users.update_one({"email": email}, {"$set": {"password_hash": generate_password_hash(password)}})
        session.pop("reset_email", None)
        flash("Password reset. Please sign in.", "success")
        return redirect(url_for("login"))
    return render_template("auth/reset_password.html", email=email)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/setup-profile", methods=["GET", "POST"])
@login_required
def setup_profile():
    if request.method == "POST":
        data = request.form.to_dict()
        ok, errors = validate_profile(data)
        if not ok:
            for v in errors.values():
                flash(v, "danger")
            return render_template("profile/setup.html", profile=doc(safe_find_one('profiles', {"user_id": current_user.id})))
        payload = {
            "user_id": current_user.id,
            "age": to_int(data.get("age"), 25),
            "gender": data.get("gender", "male"),
            "height_cm": to_float(data.get("height_cm"), 170),
            "weight_kg": to_float(data.get("weight_kg"), 70),
            "medical": data.get("medical", "none"),
            "allergies": data.get("allergies", ""),
            "medications": data.get("medications", ""),
            "injuries": data.get("injuries", ""),
            "primary_goal": data.get("primary_goal", "maintain_fitness"),
            "target_weight": to_float(data.get("target_weight"), 0),
            "timeframe": data.get("timeframe", "3_months"),
            "activity_level": data.get("activity_level", "lightly_active"),
            "working_hours": to_int(data.get("working_hours"), 8),
            "sitting_hours": to_int(data.get("sitting_hours"), 6),
            "sleep_hours": to_float(data.get("sleep_hours"), 7),
            "stress_level": data.get("stress_level", "medium"),
            "food_type": data.get("food_type", "vegetarian"),
            "budget": data.get("budget", "medium"),
            "meal_frequency": data.get("meal_frequency", "3_meals"),
            "cuisine": data.get("cuisine", "mixed"),
            "fitness_level": data.get("fitness_level", "beginner"),
            "exercise_habit": data.get("exercise_habit", ""),
            "updated_at": now_utc(),
        }
        safe_update_one('profiles', {"user_id": current_user.id}, {"$set": payload, "$setOnInsert": {"created_at": now_utc()}}, upsert=True)
        award_activity(current_user.id, 25)
        flash("Profile saved! Your personalised plan is ready.", "success")
        return redirect(url_for("dashboard"))
    existing = doc(mongo.db.profiles.find_one({"user_id": current_user.id}))
    return render_template("profile/setup.html", profile=existing)


@app.route("/dashboard")
@login_required
def dashboard():
    profile = doc(mongo.db.profiles.find_one({"user_id": current_user.id}))
    app.logger.debug("Dashboard profile: %s", profile.to_dict() if profile else None)
    if not profile:
        flash("Please complete your profile first.", "info")
        return redirect(url_for("setup_profile"))

    p_dict = profile_to_dict(profile)
    metrics = full_health_report(p_dict)
    logs = list(mongo.db.daily_logs.find({"user_id": current_user.id}).sort("log_date", -1).limit(14))
    logs.reverse()
    habits = list(mongo.db.habits.find({"user_id": current_user.id}).sort("log_date", -1).limit(14))
    habits.reverse()
    diet_logs = list(mongo.db.diet_logs.find({"user_id": current_user.id}).sort("created_at", -1).limit(20))
    mood_logs = list(mongo.db.mood_logs.find({"user_id": current_user.id}).sort("log_date", -1).limit(14))
    mood_logs.reverse()
    today = date.today().isoformat()
    today_log = doc(mongo.db.daily_logs.find_one({"user_id": current_user.id, "log_date": today}))
    today_habit = doc(mongo.db.habits.find_one({"user_id": current_user.id, "log_date": today}))
    today_food = summarize_food(diet_logs, today)
    prediction = predict_progress(profile, metrics, logs)
    risks = health_risks(profile, metrics, habits)
    achievement_state = get_achievements(current_user.id)

    chart_data = {
        "dates": [l.get("log_date") for l in logs],
        "weights": [l.get("weight_kg", 0) for l in logs],
        "calories": [l.get("calories_consumed", 0) for l in logs],
        "burned": [l.get("calories_burned", 0) for l in logs],
        "steps": [l.get("steps", 0) for l in logs],
        "water": [l.get("water_litres", 0) for l in logs],
        "prediction_dates": prediction["dates"],
        "prediction_weights": prediction["weights"],
        "mood_dates": [m.get("log_date") for m in mood_logs],
        "mood_scores": [m.get("mood_score", 3) for m in mood_logs],
        "macro_labels": ["Protein", "Carbs", "Fat"],
        "macro_values": [today_food["protein_g"], today_food["carbs_g"], today_food["fat_g"]],
    }

    return render_template(
        "dashboard.html",
        profile=profile,
        metrics=metrics,
        chart_data=json.dumps(chart_data),
        today_log=today_log,
        today_habit=today_habit,
        today_food=today_food,
        prediction=prediction,
        risks=risks,
        achievements=achievement_state,
        notifications=build_notifications(today_habit, today_log, profile),
    )


@app.route("/log-daily", methods=["POST"])
@login_required
def log_daily():
    data = request.get_json() or request.form.to_dict()
    today = date.today().isoformat()
    payload = {
        "user_id": current_user.id,
        "log_date": today,
        "steps": to_int(data.get("steps"), 0),
        "water_litres": to_float(data.get("water"), 0),
        "calories_consumed": to_int(data.get("calories"), 0),
        "calories_burned": to_int(data.get("calories_burned"), 0),
        "weight_kg": to_float(data.get("weight"), 0),
        "updated_at": now_utc(),
    }
    mongo.db.daily_logs.update_one(
        {"user_id": current_user.id, "log_date": today},
        {"$set": payload, "$setOnInsert": {"created_at": now_utc()}},
        upsert=True,
    )
    mongo.db.habits.update_one(
        {"user_id": current_user.id, "log_date": today},
        {"$set": {
            "user_id": current_user.id,
            "log_date": today,
            "water_glasses": to_int(data.get("water_glasses"), int(payload["water_litres"] * 4)),
            "sleep_hours": to_float(data.get("sleep_hours"), 0),
            "steps": payload["steps"],
            "exercise_completed": str(data.get("exercise_completed", "")).lower() in {"on", "true", "yes", "1"},
            "mood": data.get("mood", "neutral"),
            "updated_at": now_utc(),
        }, "$setOnInsert": {"created_at": now_utc()}},
        upsert=True,
    )
    award_activity(current_user.id, 15)
    unlock_badges(current_user.id)
    if request.is_json:
        return jsonify({"status": "ok", "message": "Log updated!"})
    flash("Daily log updated!", "success")
    return redirect(url_for("dashboard"))


@app.route("/log-food", methods=["POST"])
@login_required
def log_food():
    data = request.get_json() or request.form.to_dict()
    food_name = data.get("food_name", "").strip()
    if not food_name:
        return jsonify({"status": "error", "message": "Food name is required."}), 400
    payload = {
        "user_id": current_user.id,
        "log_date": date.today().isoformat(),
        "meal": data.get("meal", "snack"),
        "food_name": food_name,
        "calories": to_int(data.get("calories"), estimate_food(food_name)["calories"]),
        "protein_g": to_float(data.get("protein_g"), estimate_food(food_name)["protein_g"]),
        "carbs_g": to_float(data.get("carbs_g"), estimate_food(food_name)["carbs_g"]),
        "fat_g": to_float(data.get("fat_g"), estimate_food(food_name)["fat_g"]),
        "created_at": now_utc(),
    }
    mongo.db.diet_logs.insert_one(payload)
    award_activity(current_user.id, 10)
    unlock_badges(current_user.id)
    response_food = dict(payload)
    response_food.pop("created_at", None)
    response_food.pop("_id", None)
    return jsonify({"status": "ok", "message": "Meal added.", "food": response_food})


@app.route("/log-mood", methods=["POST"])
@login_required
def log_mood():
    data = request.get_json() or request.form.to_dict()
    mood = data.get("mood", "neutral")
    payload = {
        "user_id": current_user.id,
        "log_date": date.today().isoformat(),
        "mood": mood,
        "mood_score": mood_score(mood),
        "stress": to_int(data.get("stress"), 3),
        "journal": data.get("journal", ""),
        "meditation_minutes": to_int(data.get("meditation_minutes"), 0),
        "created_at": now_utc(),
    }
    mongo.db.mood_logs.insert_one(payload)
    award_activity(current_user.id, 10)
    return jsonify({"status": "ok", "message": "Mood journal saved."})


@app.route("/recommendations")
@login_required
def recommendations():
    profile = doc(mongo.db.profiles.find_one({"user_id": current_user.id}))
    app.logger.debug("Recommendations profile: %s", profile.to_dict() if profile else None)
    if not profile:
        return redirect(url_for("setup_profile"))
    p_dict = profile_to_dict(profile)
    metrics = full_health_report(p_dict)
    diet = get_diet_plan(p_dict, metrics)
    workout = get_workout_plan(p_dict)
    mongo.db.predictions.insert_one({
        "user_id": current_user.id,
        "kind": "recommendation_snapshot",
        "diet_totals": diet.get("totals", {}),
        "workout_goal": workout.get("goal"),
        "workout_level": workout.get("level"),
        "created_at": now_utc(),
    })
    return render_template("recommendations.html", profile=profile, metrics=metrics, diet=diet, workout=workout)


@app.route("/feedback", methods=["POST"])
@login_required
def feedback():
    data = request.get_json() or request.form.to_dict()
    weight = to_float(data.get("weight"), 0)
    mongo.db.feedback.insert_one({
        "user_id": current_user.id,
        "followed_diet": data.get("followed_diet", "no") == "yes",
        "weight_kg": weight,
        "notes": data.get("notes", ""),
        "fb_date": date.today().isoformat(),
        "created_at": now_utc(),
    })
    if weight > 0:
        mongo.db.profiles.update_one({"user_id": current_user.id}, {"$set": {"weight_kg": weight, "updated_at": now_utc()}})
    award_activity(current_user.id, 10)
    return jsonify({"status": "ok", "message": "Feedback recorded. Plan will adapt!"})


@app.route("/chatbot")
@login_required
def chatbot():
    profile = doc(mongo.db.profiles.find_one({"user_id": current_user.id}))
    history = list(mongo.db.chat_history.find({"user_id": current_user.id}).sort("created_at", -1).limit(10))
    history.reverse()
    return render_template("chatbot.html", profile=profile, history=history)


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if not message:
        return jsonify({"reply": "Tell me what you want to work on today."})

    profile = doc(mongo.db.profiles.find_one({"user_id": current_user.id}))
    p_dict = profile_to_dict(profile) if profile else {}
    metrics = full_health_report(p_dict) if p_dict else {}
    recent_logs = list(mongo.db.daily_logs.find({"user_id": current_user.id}).sort("log_date", -1).limit(7))
    habits = list(mongo.db.habits.find({"user_id": current_user.id}).sort("log_date", -1).limit(7))
    workouts = list(mongo.db.workouts.find({"user_id": current_user.id}).sort("created_at", -1).limit(5))

    system_prompt = personalized_prompt(p_dict, metrics, recent_logs, habits, workouts)
    api_key = app.config.get("OPENAI_API_KEY", "")
    model = app.config.get("OPENAI_MODEL", "gpt-4.1-mini")
    try:
        reply = call_openai_response(api_key, model, system_prompt, history, message) if api_key else rule_based_chat(message, p_dict, metrics, habits)
    except Exception as e:
        app.logger.warning("[chat] OpenAI request failed: %s", e)
        reply = rule_based_chat(message, p_dict, metrics, habits)

    mongo.db.chat_history.insert_one({
        "user_id": current_user.id,
        "message": message,
        "reply": reply,
        "context": {"bmi": metrics.get("bmi"), "goal": p_dict.get("primary_goal")},
        "created_at": now_utc(),
    })
    return jsonify({"reply": reply})


def call_openai_response(api_key, model, system_prompt, history, message):
    client = OpenAI(api_key=api_key)
    conversation = []
    for item in history[-10:]:
        role = item.get("role", "user")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            conversation.append({"role": role, "content": [{"type": "input_text", "text": content}]})
    conversation.append({"role": "user", "content": [{"type": "input_text", "text": message}]})
    response = client.responses.create(model=model, instructions=system_prompt, input=conversation, max_output_tokens=300)
    reply = getattr(response, "output_text", "").strip()
    if not reply:
        raise RuntimeError("OpenAI API returned an empty response")
    return reply


def personalized_prompt(profile, metrics, logs, habits, workouts):
    return f"""You are a professional AI health and fitness coach.

Use this user's real context:
- BMI: {metrics.get('bmi', 'N/A')} ({metrics.get('bmi_cat', 'N/A')})
- Weight: {profile.get('weight_kg', 'N/A')} kg
- Goal: {profile.get('primary_goal', 'N/A')}
- Activity level: {profile.get('activity_level', 'N/A')}
- Calorie target: {metrics.get('target_cal', 'N/A')} kcal
- Recent logs: {logs}
- Recent habits: {habits}
- Workout history: {workouts}

Give practical, personalized advice under 150 words. Do not diagnose disease; recommend medical care for serious symptoms."""


def rule_based_chat(message, profile, metrics, habits=None):
    msg = message.lower()
    goal = profile.get("primary_goal", "maintain_fitness")
    latest_habit = (habits or [{}])[0] if habits else {}
    if "belly fat" in msg or "fat loss" in msg:
        return (f"Based on your BMI of {metrics.get('bmi', 'N/A')} and goal, start with a 300 kcal daily deficit "
                "and combine cardio with strength training 4 times/week. Keep protein high, avoid sugary drinks, "
                f"and aim for 8,000 steps. Your current sleep log is {latest_habit.get('sleep_hours', 'not logged')} hours.")
    if any(x in msg for x in ["calorie", "kcal"]):
        return f"Your daily calorie target is {metrics.get('target_cal', 'N/A')} kcal, based on TDEE {metrics.get('tdee', 'N/A')} kcal."
    if any(x in msg for x in ["bmi", "weight", "overweight"]):
        return f"Your BMI is {metrics.get('bmi', 'N/A')} ({metrics.get('bmi_cat', 'N/A')}). Track weight weekly and focus on consistency."
    if any(x in msg for x in ["workout", "exercise", "gym", "training"]):
        return f"For {goal.replace('_', ' ')}, train 4-5 days/week with strength plus light cardio. Mark workouts complete to build your streak."
    if any(x in msg for x in ["protein", "macro"]):
        macros = metrics.get("macros", {})
        return f"Macro targets: protein {macros.get('protein_g','N/A')}g, carbs {macros.get('carbs_g','N/A')}g, fat {macros.get('fat_g','N/A')}g."
    if any(x in msg for x in ["sleep", "stress", "mood"]):
        return "Aim for 7-9 hours of sleep, 5 minutes of breathing practice, and log your mood so your dashboard can spot patterns."
    return "I can help with calories, fat loss, workouts, macros, hydration, sleep, stress, and meal choices based on your profile."


def profile_to_dict(profile):
    data = as_dict(profile)
    app.logger.debug("profile_to_dict input: %s", data)
    goal = data.get("primary_goal", data.get("goal", "maintain_fitness"))
    food_type = data.get("food_type", data.get("food_preference", "vegetarian"))
    result = {
        "age": data.get("age", 25),
        "gender": data.get("gender", "male"),
        "height_cm": data.get("height_cm", data.get("height", 170)),
        "weight_kg": data.get("weight_kg", data.get("weight", 70)),
        "medical": data.get("medical", "none"),
        "medical_conditions": data.get("medical_conditions", data.get("medical", "none")),
        "allergies": data.get("allergies", ""),
        "medications": data.get("medications", ""),
        "injuries": data.get("injuries", ""),
        "primary_goal": goal,
        "goal": goal,
        "activity_level": data.get("activity_level", "lightly_active"),
        "food_type": food_type,
        "food_preference": food_type,
        "cuisine": data.get("cuisine", "mixed"),
        "meal_frequency": data.get("meal_frequency", "3_meals"),
        "fitness_level": data.get("fitness_level", "beginner"),
        "exercise_habit": data.get("exercise_habit", ""),
        "workout_frequency": data.get("workout_frequency", data.get("exercise_habit", "")),
        "target_weight": data.get("target_weight", 0),
        "stress_level": data.get("stress_level", "medium"),
        "sleep_hours": data.get("sleep_hours", 7),
        "working_hours": data.get("working_hours", 8),
        "sitting_hours": data.get("sitting_hours", 6),
    }
    app.logger.debug("profile_to_dict output: %s", result)
    return result


def predict_progress(profile, metrics, logs):
    current_weight = to_float(profile.get("weight_kg"), 70)
    dated_weights = [(i, to_float(l.get("weight_kg"), 0)) for i, l in enumerate(logs) if to_float(l.get("weight_kg"), 0) > 0]
    if len(dated_weights) >= 2:
        x = np.array([[i] for i, _ in dated_weights])
        y = np.array([w for _, w in dated_weights])
        model = LinearRegression().fit(x, y)
        day7 = float(model.predict([[len(logs) + 7]])[0])
        day30 = float(model.predict([[len(logs) + 30]])[0])
    else:
        daily_delta = -0.05 if "loss" in profile.get("primary_goal", "") else 0.03 if "gain" in profile.get("primary_goal", "") else 0
        day7 = current_weight + daily_delta * 7
        day30 = current_weight + daily_delta * 30
    avg_burned = int(np.mean([l.get("calories_burned", 0) for l in logs]) if logs else metrics.get("tdee", 0) * 0.15)
    dates = [(date.today() + timedelta(days=d)).isoformat() for d in (0, 7, 30)]
    return {
        "current_weight": round(current_weight, 1),
        "weight_7": round(max(day7, 0), 1),
        "weight_30": round(max(day30, 0), 1),
        "expected_burned": avg_burned,
        "trend": "Improving" if day30 <= current_weight else "Building",
        "dates": dates,
        "weights": [round(current_weight, 1), round(max(day7, 0), 1), round(max(day30, 0), 1)],
    }


def health_risks(profile, metrics, habits):
    bmi = to_float(metrics.get("bmi"), 0)
    latest_steps = habits[-1].get("steps", 0) if habits else 0
    stress = profile.get("stress_level", "medium")
    return {
        "obesity": risk("High" if bmi >= 30 else "Medium" if bmi >= 25 else "Low", "Maintain a calorie target and strength train weekly."),
        "diabetes": risk("High" if bmi >= 30 and latest_steps < 4000 else "Medium" if bmi >= 25 else "Low", "Prioritize fiber, protein, walking after meals, and routine checkups."),
        "heart": risk("High" if bmi >= 30 and stress == "high" else "Medium" if latest_steps < 5000 else "Low", "Improve steps, sleep, hydration, and steady cardio."),
    }


def risk(level, recommendation):
    return {"level": level, "recommendation": recommendation}


def summarize_food(diet_logs, today):
    items = [x for x in diet_logs if x.get("log_date") == today]
    return {
        "items": items,
        "calories": sum(to_int(x.get("calories"), 0) for x in items),
        "protein_g": round(sum(to_float(x.get("protein_g"), 0) for x in items), 1),
        "carbs_g": round(sum(to_float(x.get("carbs_g"), 0) for x in items), 1),
        "fat_g": round(sum(to_float(x.get("fat_g"), 0) for x in items), 1),
    }


def estimate_food(name):
    catalog = {
        "rice": {"calories": 200, "protein_g": 4, "carbs_g": 45, "fat_g": 1},
        "dal": {"calories": 180, "protein_g": 10, "carbs_g": 26, "fat_g": 4},
        "egg": {"calories": 78, "protein_g": 6, "carbs_g": 1, "fat_g": 5},
        "paneer": {"calories": 265, "protein_g": 18, "carbs_g": 6, "fat_g": 20},
        "chicken": {"calories": 240, "protein_g": 35, "carbs_g": 0, "fat_g": 8},
        "banana": {"calories": 105, "protein_g": 1, "carbs_g": 27, "fat_g": 0},
    }
    lower = name.lower()
    for key, value in catalog.items():
        if key in lower:
            return value
    return {"calories": 150, "protein_g": 5, "carbs_g": 20, "fat_g": 5}


def build_notifications(habit, daily_log, profile):
    notes = []
    if not habit or habit.get("water_glasses", 0) < 8:
        notes.append("Drink water")
    if not habit or not habit.get("exercise_completed"):
        notes.append("Workout reminder")
    if habit and 0 < habit.get("sleep_hours", 0) < 7:
        notes.append("Sleep reminder")
    if profile.get("stress_level") == "high":
        notes.append("Try 5 minutes of breathing")
    return notes


def get_achievements(user_id):
    try:
        user = mongo.db.users.find_one({"_id": oid(user_id)}) or {}
    except PyMongoError as e:
        app.logger.warning("Could not load achievements: %s", e)
        user = {}
    return {"xp": user.get("xp", 0), "streak": user.get("streak", 0), "badges": user.get("badges", [])}


def award_activity(user_id, xp):
    try:
        today = date.today().isoformat()
        user = mongo.db.users.find_one({"_id": oid(user_id)})
        if not user:
            return
        last = user.get("last_activity_date")
        streak = user.get("streak", 0)
        if last != today:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            streak = streak + 1 if last == yesterday else 1
        mongo.db.users.update_one({"_id": oid(user_id)}, {"$set": {"last_activity_date": today, "streak": streak}, "$inc": {"xp": xp}})
    except PyMongoError as e:
        app.logger.warning("Could not award activity: %s", e)


def unlock_badges(user_id):
    try:
        user = mongo.db.users.find_one({"_id": oid(user_id)}) or {}
        badges = set(user.get("badges", []))
        if mongo.db.workouts.count_documents({"user_id": user_id}) or mongo.db.habits.count_documents({"user_id": user_id, "exercise_completed": True}):
            badges.add("First Workout")
        if user.get("streak", 0) >= 7:
            badges.add("7 Day Streak")
        if user.get("xp", 0) >= 100:
            badges.add("Fitness Beginner")
        if mongo.db.diet_logs.count_documents({"user_id": user_id}) >= 10:
            badges.add("Healthy Eating Master")
        mongo.db.users.update_one({"_id": oid(user_id)}, {"$set": {"badges": sorted(badges)}})
    except PyMongoError as e:
        app.logger.warning("Could not unlock badges: %s", e)


def mood_score(mood):
    return {"sad": 1, "stressed": 2, "neutral": 3, "happy": 4, "great": 5}.get(mood, 3)


def normalize_otp(form):
    digits = "".join(form.getlist("otp_digit")).strip()
    typed = (form.get("otp_code") or "").strip()
    return (typed or digits).replace(" ", "")


def seconds_since(value):
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=now_utc().tzinfo)
        return (now_utc() - value).total_seconds()
    except Exception:
        return 999999


if __name__ == "__main__":
    with app.app_context():
        from ml.diet_model import load_model
        load_model()
        app.logger.info("MongoDB and ML model ready.")

    # Start the development server when executed directly
    app.run(debug=app.config.get('DEBUG', False), use_reloader=False, host="0.0.0.0", port=5000)


@app.errorhandler(500)
def handle_internal_error(error):
    app.logger.exception('Internal server error: %s', error)
    return render_template('error.html', message='An internal error occurred. Please try again later.'), 500
