"""
ML Diet Recommendation Model.

Trains a small classifier that estimates how suitable a food item is
from its nutrition profile plus food/cuisine category.
"""
import os
import pickle

import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.tree import DecisionTreeClassifier


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_CANDIDATES = [
    os.path.join(BASE_DIR, 'ml', 'food_dataset.csv'),
    os.path.join(BASE_DIR, 'ml', 'food_dataset_30000.csv'),
    os.path.join(BASE_DIR, 'ml', 'diet_dataset_10000.csv'),
]
MODEL_OUT = os.path.join(BASE_DIR, 'models', 'diet_model.pkl')
MODEL_VERSION = 2
os.makedirs(os.path.join(BASE_DIR, 'models'), exist_ok=True)


def get_dataset_path():
    for path in DATASET_CANDIDATES:
        if os.path.exists(path):
            return path
    ml_dir = os.path.join(BASE_DIR, 'ml')
    for name in sorted(os.listdir(ml_dir)):
        if name.endswith('.csv') and ('diet' in name.lower() or 'food' in name.lower()):
            return os.path.join(ml_dir, name)
    raise FileNotFoundError("No supported food dataset found in ml/")


def _normalize_dataframe(df):
    df = df.rename(columns={'food_name': 'name', 'Food_Name': 'name'}).copy()

    required = [
        'name', 'meal_type', 'calories', 'protein_g', 'carbs_g', 'fat_g',
        'food_type', 'cuisine', 'is_healthy',
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")

    if 'tags' not in df.columns:
        df['tags'] = 'balanced'

    for col in ['name', 'meal_type', 'food_type', 'cuisine', 'tags']:
        df[col] = df[col].astype(str).str.strip()

    for col in ['calories', 'protein_g', 'carbs_g', 'fat_g', 'is_healthy']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna(subset=required).copy()

    meal_map = {
        'Breakfast': 'breakfast',
        'Lunch': 'lunch',
        'Dinner': 'dinner',
        'Snack': 'snack',
        'Snacks': 'snack',
    }
    food_map = {
        'Veg': 'vegetarian',
        'Vegetarian': 'vegetarian',
        'NonVeg': 'non_vegetarian',
        'Non-Veg': 'non_vegetarian',
        'Non Vegetarian': 'non_vegetarian',
        'Vegan': 'vegan',
    }
    cuisine_map = {
        'Indian': 'mixed',
        'Mixed': 'mixed',
        'North Indian': 'north_indian',
        'South Indian': 'south_indian',
    }

    df['meal_type'] = df['meal_type'].replace(meal_map).str.lower()
    df['food_type'] = df['food_type'].replace(food_map).str.lower().str.replace(' ', '_')
    df['cuisine'] = df['cuisine'].replace(cuisine_map).str.lower().str.replace(' ', '_')
    df['tags'] = df['tags'].str.lower().str.replace(' ', '_')
    df['name'] = df['name'].str.strip()
    df['is_healthy'] = df['is_healthy'].astype(int)

    valid_meals = {'breakfast', 'lunch', 'dinner', 'snack'}
    valid_foods = {'vegetarian', 'vegan', 'non_vegetarian'}
    valid_cuisines = {'mixed', 'north_indian', 'south_indian'}
    df = df[
        df['meal_type'].isin(valid_meals)
        & df['food_type'].isin(valid_foods)
        & df['cuisine'].isin(valid_cuisines)
    ].copy()

    canonical_cols = [
        'name', 'meal_type', 'calories', 'protein_g', 'carbs_g', 'fat_g',
        'food_type', 'cuisine', 'is_healthy', 'tags',
    ]
    df = df.drop_duplicates(subset=canonical_cols, keep='first').copy()

    return df.reset_index(drop=True)


def load_data():
    dataset_path = get_dataset_path()
    df = _normalize_dataframe(pd.read_csv(dataset_path))

    le_meal = LabelEncoder().fit(df['meal_type'])
    le_food = LabelEncoder().fit(df['food_type'])
    le_cuisine = LabelEncoder().fit(df['cuisine'])

    df['meal_enc'] = le_meal.transform(df['meal_type'])
    df['food_enc'] = le_food.transform(df['food_type'])
    df['cuis_enc'] = le_cuisine.transform(df['cuisine'])

    encoders = {'meal': le_meal, 'food': le_food, 'cuisine': le_cuisine}
    return df, encoders, dataset_path


def train_model():
    df, encoders, dataset_path = load_data()

    X = df[['calories', 'protein_g', 'carbs_g', 'fat_g', 'food_enc', 'cuis_enc']].values
    y = df['is_healthy'].values
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    clf = DecisionTreeClassifier(max_depth=5, random_state=42)
    clf.fit(X_train, y_train)

    acc = accuracy_score(y_test, clf.predict(X_test))
    import logging
    logging.getLogger(__name__).info("[diet_model] Training accuracy: %.1f%%", acc * 100)

    bundle = {
        'model': clf,
        'encoders': encoders,
        'df': df,
        'dataset_path': dataset_path,
        'model_version': MODEL_VERSION,
    }
    with open(MODEL_OUT, 'wb') as f:
        pickle.dump(bundle, f)

    logging.getLogger(__name__).info("[diet_model] Model saved -> %s", MODEL_OUT)
    return bundle


def load_model():
    dataset_path = get_dataset_path()

    if not os.path.exists(MODEL_OUT):
        return train_model()

    if os.path.getmtime(MODEL_OUT) < os.path.getmtime(dataset_path):
        return train_model()

    with open(MODEL_OUT, 'rb') as f:
        bundle = pickle.load(f)

    expected_cols = {
        'name', 'meal_type', 'calories', 'protein_g', 'carbs_g', 'fat_g',
        'food_type', 'cuisine', 'is_healthy', 'tags',
    }

    if not isinstance(bundle, dict) or 'df' not in bundle or 'model' not in bundle:
        return train_model()
    if not expected_cols.issubset(set(bundle['df'].columns)):
        return train_model()
    if bundle.get('dataset_path') != dataset_path:
        return train_model()
    if bundle.get('model_version') != MODEL_VERSION:
        return train_model()

    return bundle


if __name__ == '__main__':
    train_model()
