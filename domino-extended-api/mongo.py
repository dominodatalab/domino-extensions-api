import os
import logging

from pymongo import MongoClient  # type: ignore
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def create_database_connection():
    if os.environ.get("MONGO_PASSWORD") is None:
        return []

    platform_namespace = os.environ.get(
        "PLATFORM_NAMESPACE", "domino-platform"
    )
    host = os.environ.get(
        "MONGO_HOST",
        f"mongodb-replicaset.{platform_namespace}.svc.cluster.local:27017",
    )

    username = quote_plus(os.environ.get("MONGO_USERNAME", "admin"))
    password = quote_plus(os.environ["MONGO_PASSWORD"])

    db_name = quote_plus(os.environ.get("MONGO_DB_NAME", "domino"))
    if username == "admin":
        path = ""
    else:
        path = "/{}".format(db_name)
    mongo_uri = "mongodb://{}:{}@{}{}".format(username, password, host, path)

    return MongoClient(mongo_uri)[db_name]


MONGO_DATABASE = create_database_connection()