"""
Health Calculations Module
Formulas:
  BMI  = weight(kg) / height(m)^2
  BMR  = Harris-Benedict equation (different for M/F)
  TDEE = BMR × activity multiplier
"""

def calculate_bmi(weight_kg, height_cm):
    """Returns BMI value and category."""
    weight_kg = float(weight_kg)
    height_cm = float(height_cm)
    h = height_cm / 100
    bmi = round(weight_kg / (h * h), 1)
    if bmi < 18.5:
        cat = "Underweight"
    elif bmi < 25:
        cat = "Normal weight"
    elif bmi < 30:
        cat = "Overweight"
    else:
        cat = "Obese"
    return bmi, cat


def calculate_bmr(weight_kg, height_cm, age, gender):
    """
    Harris-Benedict BMR formula.
    Male:   BMR = 88.36 + (13.4 × w) + (4.8 × h) - (5.7 × age)
    Female: BMR = 447.6 + (9.2 × w) + (3.1 × h) - (4.3 × age)
    """
    weight_kg = float(weight_kg)
    height_cm = float(height_cm)
    age = int(age)
    if str(gender).lower() in ('male', 'm'):
        bmr = 88.36 + (13.4 * weight_kg) + (4.8 * height_cm) - (5.7 * age)
    else:
        bmr = 447.6 + (9.2 * weight_kg) + (3.1 * height_cm) - (4.3 * age)
    return round(bmr, 0)


def calculate_tdee(bmr, activity_level):
    """
    TDEE = BMR × activity multiplier
    activity_level: sedentary | lightly_active | moderately_active | very_active
    """
    multipliers = {
        'sedentary':          1.2,
        'lightly_active':     1.375,
        'moderately_active':  1.55,
        'very_active':        1.725,
        'extra_active':       1.9,
    }
    mult = multipliers.get(str(activity_level).lower(), 1.375)
    return round(bmr * mult, 0)


def calorie_target(tdee, goal):
    """
    Adjust TDEE for goal:
      weight_loss   → deficit 500 kcal/day
      muscle_gain   → surplus 300 kcal/day
      maintain / improve_stamina → TDEE
    """
    goal = str(goal).lower()
    if goal == 'weight_loss':
        return max(1200, tdee - 500)
    elif goal in ('muscle_gain', 'weight_gain'):
        return tdee + 300
    return tdee


def macro_split(calories, goal):
    """
    Returns protein/carbs/fat grams based on goal.
    """
    splits = {
        'weight_loss':       (0.35, 0.40, 0.25),
        'muscle_gain':       (0.35, 0.45, 0.20),
        'weight_gain':       (0.35, 0.45, 0.20),
        'maintain_fitness':  (0.25, 0.50, 0.25),
        'maintenance':       (0.25, 0.50, 0.25),
        'improve_stamina':   (0.20, 0.55, 0.25),
    }
    p_ratio, c_ratio, f_ratio = splits.get(str(goal).lower(), (0.25, 0.50, 0.25))
    return {
        'protein_g': round((calories * p_ratio) / 4),
        'carbs_g':   round((calories * c_ratio) / 4),
        'fat_g':     round((calories * f_ratio) / 9),
    }


def full_health_report(profile):
    """
    Given a user profile dict, return all calculated metrics.
    """
    import logging
    logging.getLogger(__name__).debug("Health calculation input profile: %s", profile)
    weight = profile.get('weight_kg', profile.get('weight', 70))
    height = profile.get('height_cm', profile.get('height', 170))
    age = profile.get('age', 25)
    gender = profile.get('gender', 'male')
    activity = profile.get('activity_level', 'lightly_active')
    goal = profile.get('primary_goal', profile.get('goal', 'maintain_fitness'))

    bmi, bmi_cat  = calculate_bmi(weight, height)
    bmr            = calculate_bmr(weight, height, age, gender)
    tdee           = calculate_tdee(bmr, activity)
    target_cal     = calorie_target(tdee, goal)
    macros         = macro_split(target_cal, goal)

    return {
        'bmi':        bmi,
        'bmi_cat':    bmi_cat,
        'bmr':        int(bmr),
        'tdee':       int(tdee),
        'target_cal': int(target_cal),
        'macros':     macros,
    }
