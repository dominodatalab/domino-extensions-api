"""Domino domsed_api module Module.

This module implements a functions/endpoints for domsed api.

Example:
    List mutation(GET) : /mutation/list
    Get mutation(GET) : /mutation/<name>

    domino_system_cred.get_mongo_creds()
"""

from flask import request, Response, Blueprint  # type: ignore
import logging
from kubernetes import client, config
from kubernetes.client import ApiClient, CustomObjectsApi

import os
import utils

domsed_api = Blueprint("domsed_api", __name__)

DEFAULT_PLATFORM_NAMESPACE = "domino-platform"
k8s_api_client = None
k8s_api = None
group = "apps.dominodatalab.com"
version = "v1alpha1"
platform_namespace = ""
plural = "mutations"


lvl: str = logging.getLevelName(os.environ.get("LOG_LEVEL", "WARNING"))
logging.basicConfig(
    level=lvl,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("extendedapi_server_domsed")
logger.setLevel(logging.WARNING)

try:
    config.load_incluster_config()
except config.ConfigException:
    try:
        config.load_kube_config()
    except config.ConfigException:
        raise Exception("Could not configure kubernetes python client")

k8s_api_client: ApiClient = client.ApiClient()
k8s_api: CustomObjectsApi = client.CustomObjectsApi(k8s_api_client)

platform_namespace: str = os.environ.get(
    "PLATFORM_NAMESPACE", DEFAULT_PLATFORM_NAMESPACE
)
debug: bool = os.environ.get("FLASK_ENV") == "development"


@domsed_api.route("/mutation/apply", methods=["POST"])
def apply_mutation() -> object:
    try:
        mutation = request.get_json()
        logging.warning(mutation)
        if utils.is_user_authorized(utils.get_headers(request.headers)):

            logging.warning(
                "First Delete before apply mutation if it exists:"
                + mutation["metadata"]["name"]
            )
            delete_mutation(mutation["metadata"]["name"])

            out: object = k8s_api.create_namespaced_custom_object(
                group, version, platform_namespace, plural, mutation
            )
            logging.warning("Mutation Added :" + mutation["metadata"]["name"])
            return out
        else:
            return Response(
                "Unauthorized to apply mutations because not an admin",
                403,
            )
    except Exception as e:
        logger.exception(e)
        logger.warning(
            f"Mutation {mutation['metadata']['name']} \
                       failed to apply"
        )


@domsed_api.route("/mutation/<name>", methods=["DELETE"])
def delete_mutation(name: str) -> object:
    try:
        logger.warning(request.headers)
        if utils.is_user_authorized(utils.get_headers(request.headers)):
            out = k8s_api.get_namespaced_custom_object(
                group, version, platform_namespace, plural, name
            )
            if out:
                out: object = k8s_api.delete_namespaced_custom_object(
                    group, version, platform_namespace, plural, name
                )
                logging.info(out)
                logging.info("Mutation Delete :" + name)
            return out
        else:
            return Response(
                "Unauthorized to delete mutations because not an admin",
                403,
            )
    except Exception as e:
        logger.exception(e)
        logger.warning(f"Mutation {name} failed to delete")


@domsed_api.route("/mutation/<name>", methods=["GET"])
def get_mutation(name: str) -> object:
    try:
        logger.warning(request.headers)
        if utils.is_user_authorized(utils.get_headers(request.headers)):
            out: object = k8s_api.get_namespaced_custom_object(
                group, version, platform_namespace, plural, name
            )
            logging.info(out)
            logging.info("Mutation Get :" + name)
            return out
        else:
            return Response(
                "Unauthorized to get mutation because not an admina",
                403,
            )
    except Exception as e:
        logger.exception(e)
        logger.warning(f"Mutation {name} failed to delete")


@domsed_api.route("/mutation/list", methods=["GET"])
def list_mutations():
    logger.warning("/mutation/list")
    try:
        logger.warning(request.headers)
        if utils.is_user_authorized(utils.get_headers(request.headers)):
            return k8s_api.list_namespaced_custom_object(
                group, version, platform_namespace, plural
            )
        else:
            return Response(
                "Unauthorized to list mutations because not an admin",
                403,
            )
    except Exception as e:
        logger.exception(e)
        logger.warning("Failed to list mutations")
