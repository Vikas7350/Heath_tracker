from typing import Tuple, Dict
from flask import current_app
from utils import valid_email, to_int, to_float


def validate_registration(form) -> Tuple[bool, Dict[str, str]]:
    errors = {}
    name = (form.get('name') or '').strip()
    email = (form.get('email') or '').strip().lower()
    password = form.get('password') or ''
    confirm = form.get('confirm_password') or ''

    if not name:
        errors['name'] = 'Name is required.'
    if not email or not valid_email(email):
        errors['email'] = 'Enter a valid email address.'
    if len(password) < 6:
        errors['password'] = 'Password must be at least 6 characters.'
    if password != confirm:
        errors['confirm_password'] = 'Passwords do not match.'

    return (len(errors) == 0, errors)


def validate_login(form) -> Tuple[bool, Dict[str, str]]:
    errors = {}
    email = (form.get('email') or '').strip().lower()
    password = form.get('password') or ''
    if not email or not valid_email(email):
        errors['email'] = 'Enter a valid email address.'
    if not password:
        errors['password'] = 'Password is required.'
    return (len(errors) == 0, errors)


def validate_profile(data) -> Tuple[bool, Dict[str, str]]:
    errors = {}
    age = data.get('age')
    try:
        a = to_int(age, None)
        if a is None or a <= 0 or a > 120:
            errors['age'] = 'Enter a valid age.'
    except Exception:
        errors['age'] = 'Enter a valid age.'
    # height and weight
    try:
        h = to_float(data.get('height_cm'), None)
        if h is None or h <= 0 or h > 300:
            errors['height_cm'] = 'Enter a valid height.'
    except Exception:
        errors['height_cm'] = 'Enter a valid height.'
    try:
        w = to_float(data.get('weight_kg'), None)
        if w is None or w <= 0 or w > 1000:
            errors['weight_kg'] = 'Enter a valid weight.'
    except Exception:
        errors['weight_kg'] = 'Enter a valid weight.'

    return (len(errors) == 0, errors)
