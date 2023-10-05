"""Domino Creds Module.

This module implements a retrieves the credentials for different components
within domino(ex mongodb,keycloak) import the module and variable d
omino_system_cred should have functions to retrive the appropriate creds.

Example:
    import domino_system_cred from domino_creds

    domino_system_cred.get_mongo_creds()
"""

import os
import logging
from kubernetes import client, config
from kubernetes.client import ApiClient, CustomObjectsApi
import base64
import json
from typing import Tuple, Dict

logger = logging.getLogger(__name__)

try:
    config.load_incluster_config()
except config.ConfigException:
    try:
        config.load_kube_config()
    except config.ConfigException:
        raise Exception("Could not configure kubernetes python client")

k8s_api_client: ApiClient = client.ApiClient()
k8s_api: CustomObjectsApi = client.CustomObjectsApi(k8s_api_client)
api_instance = client.CoreV1Api(k8s_api_client)
DEFAULT_PLATFORM_NAMESPACE = "domino-platform"
DEFAULT_SYSTEM_NAMESPACE = "domino-system"
DEFAULT_SYSTEM_FIELD = "domino-field"

credential_store_name = "credential-store-domino-platform"

cred_data = {}

platform_namespace: str = os.environ.get(
    "PLATFORM_NAMESPACE", DEFAULT_PLATFORM_NAMESPACE
)

system_namespace: str = os.environ.get("SYSTEM_NAMESPACE",
                                       DEFAULT_SYSTEM_NAMESPACE)

field_namespace: str = os.environ.get("SYSTEM_NAMESPACE",
                                      DEFAULT_SYSTEM_FIELD)


class DominoSystemCred:

    def __init__(self):
        self._cred_data = get_domino_creds_from_secret()

    def get_mongo_creds(self) -> Tuple[str, str]:
        return (
            self._cred_data["mongodb"]["admin_username"],
            self._cred_data["mongodb"]["admin_password"],
        )

    def get_mongo_creds_object(self) -> Dict:
        return self._cred_data["mongodb"]

    def get_keycloak_creds(self) -> Tuple[str, str]:
        return (
            self._cred_data["keycloak"]["username"],
            self._cred_data["keycloak"]["password"],
        )

    def get_grafana_creds(self) -> Tuple[str, str]:
        return (
            self._cred_data["grafana"]["admin_username"],
            self._cred_data["grafana"]["admin_password"],
        )

    def refresh_creds(self):
        self._cred_data = get_domino_creds_from_secret()


class MongoDBDetails:

    def __init__(self, dominosystemcred: DominoSystemCred):
        self.admin_username = dominosystemcred.get_mongo_creds_object()[
            "admin_username"
        ]
        self.admin_password = dominosystemcred.get_mongo_creds_object()[
            "admin_password"
        ]
        self.metrics_username = dominosystemcred.get_mongo_creds_object()[
            "metrics_username"
        ]
        self.metrics_password = dominosystemcred.get_mongo_creds_object()[
            "metrics_password"
        ]
        self.domino_username = dominosystemcred.get_mongo_creds_object()[
            "domino_username"
        ]
        self.domino_password = dominosystemcred.get_mongo_creds_object()[
            "domino_password"
        ]


def get_domino_creds_from_secret():
    try:
        api_response = api_instance.read_namespaced_secret(
            credential_store_name, system_namespace
        )
        cred_data_bytes = base64.b64decode(api_response.data["credentials"])
        return json.loads(cred_data_bytes.decode("utf8").replace("'", '"'))
    except Exception as e:
        logger.exception(e)
        logger.warning(f"Not able to get credentials from secret  {e}")


domino_system_cred = DominoSystemCred()
