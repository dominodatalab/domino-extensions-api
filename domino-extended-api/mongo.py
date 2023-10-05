"""mongodb Module.

This module implements a functions for creating mongodb connections.

"""
import os
import logging

from pymongo import MongoClient  # type: ignore
from urllib.parse import quote_plus
from domino_creds import MongoDBDetails, domino_system_cred


logger = logging.getLogger(__name__)
DEFAULT_PLATFORM_NAMESPACE = "domino-platform"

platform_namespace: str = os.environ.get(
    "PLATFORM_NAMESPACE", DEFAULT_PLATFORM_NAMESPACE
)


def create_database_connection():

    host = os.environ.get(
        "MONGO_HOST",
        f"mongodb-replicaset.{platform_namespace}.svc.cluster.local:27017",
    )
    mongo_details = MongoDBDetails(domino_system_cred)
    username = quote_plus(mongo_details.admin_username)
    password = quote_plus(mongo_details.admin_password)

    db_name = quote_plus(os.environ.get("MONGO_DB_NAME", "domino"))
    if username == "admin":
        path = ""
    else:
        path = "/{}".format(db_name)
    mongo_uri = "mongodb://{}:{}@{}{}".format(username, password, host, path)

    return MongoClient(mongo_uri)[db_name]


MONGO_DATABASE = create_database_connection()
