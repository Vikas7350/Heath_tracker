from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
from flask_pymongo import PyMongo
from pymongo.errors import PyMongoError
import logging


mongo = PyMongo()


COLLECTIONS = (
    "users",
    "profiles",
    "daily_logs",
    "diet_logs",
    "workouts",
    "chat_history",
    "habits",
    "mood_logs",
    "achievements",
    "feedback",
    "predictions",
    "otp_verification",
    "pending_users",
)


def init_db(app):
    mongo.init_app(app)
    database = mongo.db
    if database is None:
        database = mongo.cx[app.config.get("MONGO_DBNAME", "health_tracker")]
    try:
        database.users.create_index("email", unique=True)
        database.pending_users.create_index("email", unique=True)
        database.pending_users.create_index("expires_at", expireAfterSeconds=0)
        database.profiles.create_index("user_id", unique=True)
        database.daily_logs.create_index([("user_id", 1), ("log_date", -1)])
        database.habits.create_index([("user_id", 1), ("log_date", -1)])
        database.diet_logs.create_index([("user_id", 1), ("log_date", -1)])
        database.mood_logs.create_index([("user_id", 1), ("log_date", -1)])
        database.chat_history.create_index([("user_id", 1), ("created_at", -1)])
        database.otp_verification.create_index("expires_at", expireAfterSeconds=0)
    except PyMongoError as exc:
        app.logger.warning("MongoDB indexes were not created yet: %s", exc)
    return database


def now_utc():
    return datetime.now(timezone.utc)


def oid(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


class MongoDocument(SimpleNamespace):
    def __init__(self, data=None, **kwargs):
        payload = dict(data or {})
        payload.update(kwargs)
        if "_id" in payload:
            payload["id"] = str(payload["_id"])
        super().__init__(**payload)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def to_dict(self):
        return dict(self.__dict__)


class MongoUser(MongoDocument):
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    @property
    def password(self):
        return getattr(self, "password_hash", "")


def doc(data):
    return MongoDocument(data) if data else None


def user_doc(data):
    return MongoUser(data) if data else None


def as_dict(value):
    if isinstance(value, MongoDocument):
        return value.to_dict()
    return dict(value or {})


def safe_find_one(collection_name, query):
    """Safe wrapper for find_one that returns None on DB errors."""
    logger = logging.getLogger(__name__)
    try:
        return mongo.db[collection_name].find_one(query)
    except PyMongoError as exc:
        logger.warning("safe_find_one failed for %s: %s", collection_name, exc)
        return None


def safe_insert_one(collection_name, doc):
    logger = logging.getLogger(__name__)
    try:
        return mongo.db[collection_name].insert_one(doc)
    except PyMongoError as exc:
        logger.warning("safe_insert_one failed for %s: %s", collection_name, exc)
        return None


def safe_update_one(collection_name, filter_query, update_doc, upsert=False):
    logger = logging.getLogger(__name__)
    try:
        return mongo.db[collection_name].update_one(filter_query, update_doc, upsert=upsert)
    except PyMongoError as exc:
        logger.warning("safe_update_one failed for %s: %s", collection_name, exc)
        return None


def safe_delete_many(collection_name, filter_query):
    logger = logging.getLogger(__name__)
    try:
        return mongo.db[collection_name].delete_many(filter_query)
    except PyMongoError as exc:
        logger.warning("safe_delete_many failed for %s: %s", collection_name, exc)
        return None
