"""
Personalized diet and workout recommendation engine.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.diet_model import load_model


FOOD_ALIASES = {
    "veg": "vegetarian",
    "vegetarian": "vegetarian",
    "nonveg": "non_vegetarian",
    "non-veg": "non_vegetarian",
    "non vegetarian": "non_vegetarian",
    "non_vegetarian": "non_vegetarian",
    "vegan": "vegan",
}

GOAL_ALIASES = {
    "maintenance": "maintain_fitness",
    "maintain": "maintain_fitness",
    "weight_gain": "muscle_gain",
}


def _goal(profile):
    value = str(profile.get("primary_goal", profile.get("goal", "maintain_fitness"))).lower()
    return GOAL_ALIASES.get(value, value)


def _food_preference(profile):
    raw = profile.get("food_type", profile.get("food_preference", "vegetarian"))
    return FOOD_ALIASES.get(str(raw).strip().lower(), "vegetarian")


def _filter_foods(df, food_type, cuisine, meal_type):
    """Strictly filter foods by selected diet preference, meal slot, and cuisine."""
    sub = df[(df["meal_type"] == meal_type) & (df["food_type"] == food_type)].copy()

    if sub.empty and meal_type == "snack":
        sub = df[(df["calories"] <= 300) & (df["food_type"] == food_type)].copy()

    if cuisine and cuisine != "mixed":
        preferred = sub[sub["cuisine"].isin([cuisine, "mixed"])]
        if not preferred.empty:
            sub = preferred

    return sub


def _predict_health_scores(bundle, sub):
    if sub.empty:
        return sub

    model = bundle["model"]
    encoders = bundle["encoders"]
    scored = sub.copy()

    scored["food_enc"] = encoders["food"].transform(scored["food_type"])
    scored["cuis_enc"] = encoders["cuisine"].transform(scored["cuisine"])
    features = scored[["calories", "protein_g", "carbs_g", "fat_g", "food_enc", "cuis_enc"]].values

    if hasattr(model, "predict_proba"):
        scored["ml_health_score"] = model.predict_proba(features)[:, 1]
    else:
        scored["ml_health_score"] = model.predict(features)
    return scored


def _goal_tag(goal):
    return {
        "weight_loss": "weight_loss",
        "muscle_gain": "muscle_gain",
        "maintain_fitness": "balanced",
        "improve_stamina": "balanced",
    }.get(goal, "balanced")


def _sum_combo(combo, field):
    return sum(float(item[field]) for item in combo)


def _score_combo(combo, calorie_budget, macro_budget, goal):
    calories = _sum_combo(combo, "calories")
    protein = _sum_combo(combo, "protein_g")
    carbs = _sum_combo(combo, "carbs_g")
    fat = _sum_combo(combo, "fat_g")
    calorie_fit = max(0.0, 1 - abs(calories - calorie_budget) / max(calorie_budget, 1))
    protein_fit = max(0.0, 1 - abs(protein - macro_budget["protein_g"]) / max(macro_budget["protein_g"], 1))
    carb_fit = max(0.0, 1 - abs(carbs - macro_budget["carbs_g"]) / max(macro_budget["carbs_g"], 1))
    fat_fit = max(0.0, 1 - abs(fat - macro_budget["fat_g"]) / max(macro_budget["fat_g"], 1))
    tag_score = sum(1 for item in combo if _goal_tag(goal) in str(item.get("tags", ""))) / len(combo)
    health_score = sum(float(item.get("ml_health_score", item.get("is_healthy", 0))) for item in combo) / len(combo)

    goal_bonus = 0.0
    if goal == "weight_loss":
        goal_bonus = min(protein / max(calories, 1) * 30, 1.5)
    elif goal == "muscle_gain":
        goal_bonus = min(protein / max(macro_budget["protein_g"], 1), 1.5)

    return (
        calorie_fit * 3.0
        + protein_fit * 2.2
        + carb_fit * 0.8
        + fat_fit * 0.8
        + tag_score * 1.2
        + health_score * 1.5
        + goal_bonus
    )


def _build_meal_item(combo, meal_type, score):
    food_types = {item["food_type"] for item in combo}
    cuisines = {item["cuisine"] for item in combo}
    tags = []
    for item in combo:
        for tag in str(item.get("tags", "")).split("|"):
            tag = tag.strip()
            if tag and tag not in tags:
                tags.append(tag)
    return {
        "name": " + ".join(item["name"] for item in combo),
        "meal_type": meal_type,
        "calories": int(round(_sum_combo(combo, "calories"))),
        "protein_g": round(_sum_combo(combo, "protein_g"), 1),
        "carbs_g": round(_sum_combo(combo, "carbs_g"), 1),
        "fat_g": round(_sum_combo(combo, "fat_g"), 1),
        "food_type": next(iter(food_types)) if len(food_types) == 1 else "mixed",
        "cuisine": next(iter(cuisines)) if len(cuisines) == 1 else "mixed",
        "is_healthy": 1 if all(int(item.get("is_healthy", 0)) for item in combo) else 0,
        "tags": "|".join(tags[:4]) or "balanced",
        "score": round(score, 3),
        "items": [
            {
                "name": item["name"],
                "calories": int(round(float(item["calories"]))),
                "protein_g": round(float(item["protein_g"]), 1),
                "carbs_g": round(float(item["carbs_g"]), 1),
                "fat_g": round(float(item["fat_g"]), 1),
                "food_type": item["food_type"],
            }
            for item in combo
        ],
    }


def _pick_meal(bundle, df, food_type, cuisine, meal_type, calorie_budget, macro_budget, goal, used_names):
    sub = _filter_foods(df, food_type, cuisine, meal_type)
    sub = sub[~sub["name"].isin(used_names)]
    if sub.empty:
        return None

    sub = _predict_health_scores(bundle, sub)
    low = calorie_budget * (0.45 if goal == "weight_loss" else 0.55)
    high = calorie_budget * (1.15 if goal == "weight_loss" else 1.35)
    tight = sub[sub["calories"].between(low, high)].copy()
    if not tight.empty:
        sub = tight

    records = (
        sub.sort_values(["protein_g", "is_healthy", "calories"], ascending=[False, False, False])
        .drop_duplicates(subset=["name"], keep="first")
        .head(16)
        .to_dict(orient="records")
    )
    combos = [[item] for item in records]
    if goal != "weight_loss" or calorie_budget >= 650:
        for i, first in enumerate(records):
            for second in records[i + 1:]:
                if first["name"] == second["name"]:
                    continue
                total = float(first["calories"]) + float(second["calories"])
                if total <= calorie_budget * 1.35:
                    combos.append([first, second])

    scored_records = []
    for combo in combos:
        scored_records.append((_score_combo(combo, calorie_budget, macro_budget, goal), combo))
    scored_records.sort(key=lambda pair: pair[0], reverse=True)

    # Rotate among strong candidates so similar profiles still get variety without breaking constraints.
    top = scored_records[: min(8, len(scored_records))]
    choice_index = random.randrange(len(top)) if len(top) > 1 else 0
    score, combo = top[choice_index]
    return _build_meal_item(combo, meal_type, score)


def get_diet_plan(profile, metrics):
    import logging
    logging.getLogger(__name__).debug("Diet recommendation profile: %s", profile)
    bundle = load_model()
    df = bundle["df"]

    goal = _goal(profile)
    food_type = _food_preference(profile)
    cuisine = str(profile.get("cuisine", "mixed")).lower()
    frequency = profile.get("meal_frequency", "3_meals")
    target = int(metrics.get("target_cal", 2000))
    macros = metrics.get("macros", {})

    distributions = {
        "2_meals": {"breakfast": 0.35, "lunch": 0.55, "dinner": 0.0, "snack": 0.10},
        "3_meals": {"breakfast": 0.25, "lunch": 0.40, "dinner": 0.30, "snack": 0.05},
        "5_meals": {"breakfast": 0.20, "lunch": 0.30, "dinner": 0.25, "snack": 0.25},
    }
    dist = distributions.get(frequency, distributions["3_meals"])

    used = set()
    plan = {}
    totals = {"calories": 0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    for slot, ratio in dist.items():
        if ratio == 0:
            continue
        calorie_budget = target * ratio
        macro_budget = {
            "protein_g": float(macros.get("protein_g", 100)) * ratio,
            "carbs_g": float(macros.get("carbs_g", 200)) * ratio,
            "fat_g": float(macros.get("fat_g", 60)) * ratio,
        }
        meal = _pick_meal(bundle, df, food_type, cuisine, slot, calorie_budget, macro_budget, goal, used)
        if not meal:
            continue
        for item in meal.get("items", []):
            used.add(item["name"])
        plan[slot] = meal
        totals["calories"] += meal["calories"]
        totals["protein_g"] += meal["protein_g"]
        totals["carbs_g"] += meal["carbs_g"]
        totals["fat_g"] += meal["fat_g"]

    plan["totals"] = {
        "calories": int(round(totals["calories"])),
        "protein_g": round(totals["protein_g"], 1),
        "carbs_g": round(totals["carbs_g"], 1),
        "fat_g": round(totals["fat_g"], 1),
    }
    plan["food_type"] = food_type
    plan["goal"] = goal
    return plan


EXERCISE_POOLS = {
    "weight_loss": {
        "beginner": [
            ("Brisk Walking", "30 min", "-", "-", "Low-impact calorie burn"),
            ("Bodyweight Squats", "12 min", "3", "12", "Controlled tempo"),
            ("Incline Pushups", "10 min", "3", "10", "Beginner upper-body strength"),
            ("Jump Rope", "8 min", "4", "45 sec", "High impact; skip with joint pain"),
            ("Step-ups", "10 min", "3", "12 each", "Use a stable low step"),
        ],
        "intermediate": [
            ("Jogging Intervals", "25 min", "-", "2 min jog / 1 min walk", "Moderate cardio"),
            ("Kettlebell Swings", "12 min", "4", "15", "Hip hinge power"),
            ("Mountain Climbers", "8 min", "4", "30 sec", "Core and cardio"),
            ("Cycling", "35 min", "-", "-", "Joint-friendly cardio"),
            ("Dumbbell Circuit", "25 min", "4", "12", "Full-body conditioning"),
        ],
        "advanced": [
            ("Interval Running", "35 min", "-", "1 min fast / 2 min easy", "Conditioning"),
            ("Battle Ropes", "12 min", "5", "30 sec", "High intensity"),
            ("Burpees", "10 min", "5", "10", "High impact metabolic work"),
            ("Rowing Machine", "30 min", "-", "-", "Full-body cardio"),
            ("Sled Push", "15 min", "6", "20 m", "Power conditioning"),
        ],
    },
    "muscle_gain": {
        "beginner": [
            ("Pushups", "12 min", "3", "8-10", "Full range of motion"),
            ("Goblet Squats", "15 min", "3", "10", "Learn squat pattern"),
            ("Dumbbell Rows", "12 min", "3", "10 each", "Back strength"),
            ("Glute Bridges", "10 min", "3", "12", "Posterior chain"),
            ("Plank", "6 min", "3", "30 sec", "Core stability"),
        ],
        "intermediate": [
            ("Bench Press", "20 min", "4", "8-10", "Progressive overload"),
            ("Deadlift", "20 min", "4", "5", "Use good form"),
            ("Pullups", "15 min", "4", "6-8", "Use assistance if needed"),
            ("Shoulder Press", "15 min", "3", "8-10", "Overhead strength"),
            ("Barbell Squats", "20 min", "4", "8", "Compound lower body"),
        ],
        "advanced": [
            ("Heavy Deadlift", "25 min", "5", "3-5", "Strength focus"),
            ("Incline Bench Press", "20 min", "4", "6-8", "Upper chest"),
            ("Weighted Pullups", "15 min", "4", "5-6", "Advanced back work"),
            ("Romanian Deadlift", "18 min", "4", "8", "Hamstrings"),
            ("Front Squat", "20 min", "4", "6", "Quad strength"),
        ],
    },
    "maintain_fitness": {
        "beginner": [
            ("Morning Walk", "30 min", "-", "-", "Daily movement"),
            ("Yoga Flow", "20 min", "-", "-", "Mobility and breathing"),
            ("Light Cycling", "25 min", "-", "-", "Easy cardio"),
            ("Bodyweight Circuit", "18 min", "3", "10", "Balanced strength"),
        ],
        "intermediate": [
            ("Full Body Dumbbell", "35 min", "3", "12", "Balanced strength"),
            ("Jogging", "25 min", "-", "-", "Steady cardio"),
            ("Mobility Flow", "15 min", "-", "-", "Recovery"),
            ("Core Circuit", "12 min", "3", "15", "Stability"),
        ],
        "advanced": [
            ("Mixed Strength + Cardio", "45 min", "4", "10", "Compound lifts plus intervals"),
            ("Running 5K", "30 min", "-", "-", "Aerobic fitness"),
            ("Full Body Compound Lifts", "45 min", "4", "8", "Strength maintenance"),
            ("Swimming", "35 min", "-", "-", "Low-impact conditioning"),
        ],
    },
    "improve_stamina": {
        "beginner": [
            ("Brisk Walking", "40 min", "-", "-", "Build aerobic base"),
            ("Light Jogging", "15 min", "-", "-", "Easy pace"),
            ("Jumping Jacks", "8 min", "3", "20", "High impact; skip with joint pain"),
            ("Cycling", "30 min", "-", "-", "Low impact"),
        ],
        "intermediate": [
            ("Interval Running", "30 min", "-", "2 min run / 1 min walk", "Aerobic capacity"),
            ("Cycling", "45 min", "-", "-", "Endurance"),
            ("Jump Rope", "12 min", "5", "2 min", "Coordination and cardio"),
            ("Rowing", "25 min", "-", "-", "Full-body stamina"),
        ],
        "advanced": [
            ("Long-distance Running", "50 min", "-", "-", "Zone 2 base"),
            ("Stair Climbing", "20 min", "-", "-", "Cardio strength"),
            ("Swimming", "45 min", "-", "-", "Low-impact endurance"),
            ("Tempo Run", "30 min", "-", "-", "Threshold work"),
        ],
    },
}


HIGH_IMPACT_WORDS = ("jump", "burpee", "running", "jogging", "box", "sprint", "stair")


def _joint_risk(profile, bmi):
    text = " ".join([
        str(profile.get("medical", "")),
        str(profile.get("medical_conditions", "")),
        str(profile.get("injuries", "")),
    ]).lower()
    return bmi >= 30 or any(word in text for word in ["joint", "knee", "ankle", "leg", "back", "arthritis"])


def _exercise_dict(item):
    name, duration, sets, reps, notes = item
    return {"name": name, "duration": duration, "sets": sets, "reps": reps, "notes": notes}


def get_workout_plan(profile):
    import logging
    logging.getLogger(__name__).debug("Workout recommendation profile: %s", profile)
    goal = _goal(profile)
    level = str(profile.get("fitness_level", "beginner")).lower()
    age = int(profile.get("age", 25))
    weight = float(profile.get("weight_kg", 70))
    height = float(profile.get("height_cm", 170))
    bmi = weight / ((height / 100) ** 2)

    if level not in {"beginner", "intermediate", "advanced"}:
        level = "beginner"
    if age >= 55 and level == "advanced":
        level = "intermediate"

    pool = list(EXERCISE_POOLS.get(goal, EXERCISE_POOLS["maintain_fitness"])[level])
    if _joint_risk(profile, bmi):
        pool = [item for item in pool if not any(word in item[0].lower() for word in HIGH_IMPACT_WORDS)]
        pool.extend([
            ("Swimming", "30 min", "-", "-", "Joint-friendly cardio"),
            ("Stationary Cycling", "30 min", "-", "-", "Low-impact conditioning"),
            ("Chair-supported Squats", "10 min", "3", "10", "Joint-friendly strength"),
        ])

    deduped = []
    seen = set()
    for item in pool:
        if item[0] not in seen:
            deduped.append(item)
            seen.add(item[0])
    pool = deduped
    random.shuffle(pool)
    exercises = [_exercise_dict(item) for item in pool[:4]]

    weekly_schedule = {
        "Monday": "Strength + cardio" if goal != "muscle_gain" else "Upper body strength",
        "Tuesday": "Mobility or light walk",
        "Wednesday": "Full workout",
        "Thursday": "Recovery and stretching",
        "Friday": "Strength focus" if goal == "muscle_gain" else "Cardio focus",
        "Saturday": "Optional light activity",
        "Sunday": "Rest",
    }

    tips = {
        "weight_loss": f"At BMI {bmi:.1f}, keep workouts sustainable and pair training with a calorie deficit.",
        "muscle_gain": "Prioritize progressive overload and hit your protein target consistently.",
        "maintain_fitness": "Use a balanced mix of strength, cardio, mobility, and adequate recovery.",
        "improve_stamina": "Build volume gradually; most cardio should feel conversational.",
    }
    if _joint_risk(profile, bmi):
        tips[goal] += " High-impact moves were removed because of joint/BMI risk."

    return {
        "exercises": exercises,
        "weekly_schedule": weekly_schedule,
        "tip": tips.get(goal, ""),
        "level": level,
        "goal": goal,
    }
