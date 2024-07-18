"""mongodb Module.

This module implements a functions for creating mongodb connections.

"""
import os
import logging

from pymongo import MongoClient  # type: ignore
from urllib.parse import quote_plus
from domino_creds import MongoDBDetails, DominoSystemCred


logger = logging.getLogger(__name__)
DEFAULT_PLATFORM_NAMESPACE = "domino-platform"

platform_namespace: str = os.environ.get(
    "PLATFORM_NAMESPACE", DEFAULT_PLATFORM_NAMESPACE
)


def create_database_connection():

    host = f"mongodb-replicaset.{platform_namespace}.svc.cluster.local:27017"
    domino_system_cred = DominoSystemCred()
    mongo_details = MongoDBDetails(domino_system_cred)
    username = quote_plus(mongo_details.admin_username)
    password = quote_plus(mongo_details.admin_password)

    db_name = "domino"
    path = "/{}".format(db_name)
    '''
    if username == "admin":
        path = ""
    else:
        path = "/{}".format(db_name)
    '''
    mongo_uri = "mongodb://{}:{}@{}{}?authSource=admin".format(username, password, host, path)
    #logging.warning("mongo_uri :: ",mongo_uri)
    #print('---------')
    #print(mongo_uri)
    return MongoClient(mongo_uri)[db_name]




