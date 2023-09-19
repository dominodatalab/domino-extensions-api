from typing import Dict, Optional

from bson import ObjectId
from flask import Flask, request, Response  # type: ignore
import logging
import json
from urllib.parse import quote_plus
from pymongo import MongoClient  # type: ignore
import os
import sys
import requests
from mongo import MONGO_DATABASE
from domsed_api import domsed_api
import utils



DEFAULT_PLATFORM_NAMESPACE = "domino-platform"
WHO_AM_I_ENDPOINT = "v4/auth/principal"
DOMINO_NUCLEUS_URI = "http://nucleus-frontend.domino-platform:80"
ADMINS_RELATIVE_FILE_PATH = "admins/extended-api-acls"
ADMINS_FILE_PATH = ""

ENABLE_WKS_AUTO_SHUTDOWN = "enableWorkspaceAutoShutdown"
MAX_WKS_LIFETIME = "maximumWorkspaceLifetimeInSeconds"
ENABLE_SESSION_NOTIFICATIONS = "enableSessionNotifications"
SESSION_NOTIFICATION_PERIOD = "sessionNotificationPeriod"
USER_ID = "userId"

logger = logging.getLogger("extended-api")
app = Flask(__name__)
app.register_blueprint(domsed_api)


def create_database_connection():
    if os.environ.get("MONGO_PASSWORD") is None:
        return []

    platform_namespace = os.environ.get(
        "PLATFORM_NAMESPACE", DEFAULT_PLATFORM_NAMESPACE
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





def get_central_config_parameters(client: MongoClient):
    config_collection = client["config"]

    wks_auto_shutdown_enabled = False
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workspaceAutoShutdown.isEnabled",
        }
    )
    if val:
        wks_auto_shutdown_enabled = bool(val["value"])

    global_max_lifetime = 0
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workspaceAutoShutdown.globalMaximumLifetimeInSeconds",
        }
    )
    if val:
        global_max_lifetime = int(val["value"])

    global_default_lifetime = 0
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workspaceAutoShutdown.globalDefaultLifetimeInSeconds",
        }
    )
    if val:
        global_default_lifetime = int(val["value"])

    wks_notification_enabled = False
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workloadNotifications.isEnabled",
        }
    )
    if val:
        wks_notification_enabled = bool(val["value"])

    wks_notification_duration = 0
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workloadNotifications.longRunningWorkloadDefinitionInSeconds",
        }
    )
    if val:
        wks_notification_duration = int(val["value"])
    return (
        wks_auto_shutdown_enabled,
        global_max_lifetime,
        global_default_lifetime,
        wks_notification_enabled,
        wks_notification_duration,
    )


"""
1. Get all info on domino autoshutdown from central config
2. Get default val. If default val not present, use max value
3. Get all users
4. Apply default to all user, except for the exception user
5. Input docs is list of users with their timeout.
6. If exception timeout higher than max, override with max
"""


@app.route("/v4-extended/autoshutdownwksrules", methods=["POST"])
def apply_autoshutdown_rules() -> object:
    logger.warning(f'Extended API Endpoint /v4-extended/autoshutdownwksrules invoked')
    headers = utils.get_headers(request.headers)
    try:
        if not utils.is_user_authorized(headers):
            return Response(
                "Unauthorized - Must be Domino Admin or one of the allowed users",
                403,
            )
        logger.warning("Creating Mongo Connection")

        (
            wks_auto_shutdown_enabled,
            global_max_lifetime,
            global_default_lifetime,
            wks_notification_enabled,
            wks_notification_duration,
        ) = get_central_config_parameters(MONGO_DATABASE)
        logger.warning("Collected auto-shutdown values from central config")
        if not wks_auto_shutdown_enabled:
            return {
                "msg": "com.cerebro.domino.workloadNotifications.isEnabled is False. No changes made"
            }
        elif global_default_lifetime == 0:
            return {
                "msg": "com.cerebro.domino.workloadNotifications.defaultPeriodInSeconds not set. No changes made"
            }
        elif global_default_lifetime > global_max_lifetime:
            return {
                "msg": "com.cerebro.domino.workspaceAutoShutdown.globalDefaultLifetimeInSeconds is greater than "
                "com.cerebro.domino.workspaceAutoShutdown.globalMaximumLifetimeInSeconds. "
                "No changes made"
            }
        else:
            logger.warning("Start updating")
            # read payload
            user_pref_coll = MONGO_DATABASE["userPreferences"]
            payload = request.json
            domino_users = payload["users"]

            result = MONGO_DATABASE["users"].aggregate(
                [
                    {
                        "$lookup": {
                            "from": "userPreferences",
                            "localField": "_id",
                            "foreignField": "userId",
                            "as": "joinedResult",
                        }
                    }
                ]
            )

            for r in result:
                user_id = r["loginId"]["id"]
                user_preference = {}
                if user_id in domino_users:
                    wks_lifetime = int(domino_users[user_id])
                    logger.warning(
                        f"Override user {user_id} to autoshutdown in {wks_lifetime} seconds"
                    )
                elif payload["override_to_default"]:
                    wks_lifetime = global_default_lifetime
                    logger.warning(
                        f"Override user {user_id} to default autoshutdown in {wks_lifetime} seconds"
                    )
                else:
                    logger.warning(f"Do not override user {user_id}")

                if len(r["joinedResult"]) == 0:
                    user_preference["notifyAboutCollaboratorAdditions"] = True

                user_preference["userId"] = r["_id"]
                user_preference[ENABLE_WKS_AUTO_SHUTDOWN] = wks_auto_shutdown_enabled
                if wks_lifetime > 0:
                    user_preference[MAX_WKS_LIFETIME] = wks_lifetime
                else:
                    user_preference.pop(MAX_WKS_LIFETIME,-1)

                if wks_notification_enabled:
                    user_preference[
                        ENABLE_SESSION_NOTIFICATIONS
                    ] = wks_notification_enabled
                    user_preference[
                        SESSION_NOTIFICATION_PERIOD
                    ] = wks_notification_duration
                query = {"userId": r["_id"]}
                id = r["_id"]
                if wks_lifetime<0:
                    logger.warning(f"About to delete entry for user {id}")
                    result = user_pref_coll.delete_one({"userId": r["_id"]})
                    logger.warning(f"Deleted entry for user {id} - {result.deleted_count}")
                user_pref_coll.update_one(query, {"$set": user_preference}, upsert=True)
                logger.warning(f"Upserted entry for user {id}")
                print(user_preference)
            return {"msg": "Workspace Shutdown Durations Updated"}
    except Exception as e:
        logger.exception(e)
        return Response(
            str(e),
            500,
        )

def _env_cache_key(environment_id: ObjectId, version: int) -> str:
    return f"{str(environment_id)}-{version}"

def _get_docker_image_and_base_docker_image(revision_id:ObjectId,version_no:int):

    revision = ENVIRONMENT_REVISION_CACHE.get_by_environment(
        revision_id, version_no
    )
    docker_image = None
    docker_image_status_message = ""
    if revision is None:
        docker_image_status_message =  f"Could not find revision: {revision_id}-{version_no}"
        docker_image = None
        return docker_image,docker_image_status_message

    count = 0
    while True or count < 100:  # To avoid an infinite loop just in case
        count = count + 1
        if revision.docker_image is not None:
            docker_image = revision.docker_image
            docker_image_status_message = "success"
            break
        else:
            base_environment_revision_id = (
                revision.base_environment_revision_id
            )
            revision = ENVIRONMENT_REVISION_CACHE.get(
                base_environment_revision_id
            )
            if revision is None:
                docker_image_status_message = f"Could not find revision (in hierarchy)"
                docker_image = None
    return docker_image,docker_image_status_message


@app.route("/api-extended/refresh_cache", methods=["GET"])
def refresh_cache():
    ENVIRONMENT_REVISION_CACHE.refresh_cache()
    PROJECTS_CACHE.refresh_cache()
    return {"EnvironmentReviewCacheRefreshed": True,
            "ProjectsCacheRefreshed": True}

@app.route("/api-extended/environments/beta/environments", methods=["GET"])
def get_enchanced_env_revisions():
    logger.warning(f'Extended API Endpoint /api-extended/projects/beta/projects invoked')
    params = request.args
    resp = requests.get(f"{DOMINO_NUCLEUS_URI}/api/environments/beta/environments",headers=utils.get_headers(request.headers),params=params)
    new_envs=[]
    if(resp.status_code==200):
        environments = resp.json()['environments']

        for e in environments:
            env_id=e['id']
            latest_environment_revision_id = e['latestRevision']['number']
            image,status_message = _get_docker_image_and_base_docker_image(ObjectId(env_id),latest_environment_revision_id)
            e['latestRevision']['basedOnDockerImage']=image
            e['latestRevision']['basedOnDockerImageStatusMessage'] = status_message
            e['latestRevision']['availableTools']=None
            selected_environment_revision_id = e['selectedRevision']['number']
            image, status_message = _get_docker_image_and_base_docker_image(ObjectId(env_id),
                                                                            selected_environment_revision_id)
            e['selectedRevision']['basedOnDockerImage']=image
            e['selectedRevision']['basedOnDockerImageStatusMessage'] = status_message
            e['selectedRevision']['availableTools'] = None
            new_envs.append(e)
    return {'environments':new_envs}


@app.route("/api-extended/projects/beta/projects", methods=["GET"])
def get_enchanced_projects():
    logger.warning(f'Extended API Endpoint /api-extended/projects/beta/projects invoked')
    params = request.args
    resp = requests.get(f"{DOMINO_NUCLEUS_URI}/api/projects/beta/projects",headers=utils.get_headers(request.headers),params=params)
    new_projects=[]
    if(resp.status_code==200):
        projects = resp.json()['projects']

        for p in projects:
            project_id=p['id']
            if(PROJECTS_CACHE.get_by_project(ObjectId(project_id))):
                project = PROJECTS_CACHE.get_by_project(project_id)
                p['environment_id'] = str(project.environment_id)
                p['default_environment_revision_spec'] = project.default_environment_revision_spec
            new_projects.append(p)
    return {'projects':new_projects}

@app.route("/healthz")
def alive():
     
    return "{'status': 'Healthy'}"


class EnvironmentRevision:
    def __init__(self, revision: dict):
        self._id = ObjectId(revision["_id"])
        self.environment_id = revision["environmentId"]
        self.version = int(revision["metadata"]["number"])
        self.docker_image = revision["definition"].get("dockerImage")
        self.base_environment_revision_id = revision["definition"].get(
            "baseEnvironmentRevisionId"
        )

class EnvironmentRevisionCache:
    def __init__(self):
        logger.info("Initializing EnvironmentRevision cache.")
        self.cache: Dict[ObjectId, EnvironmentRevision] = {}

    def get(
        self, environment_revision_id: ObjectId
    ) -> Optional[EnvironmentRevision]:
        if environment_revision_id not in self.cache:
            self.refresh_cache()
        return self.cache.get(environment_revision_id)

    def try_get_by_environment(
        self, environment_id: ObjectId, version: int
    ) -> Optional[EnvironmentRevision]:
        for revision in self.cache.values():
            if (
                str(revision.environment_id) == str(environment_id)
                and revision.version == version
            ):
                return revision
        return None

    def get_by_environment(
        self, environment_id: ObjectId, version: int
    ) -> Optional[EnvironmentRevision]:
        revision = self.try_get_by_environment(environment_id, version)
        if revision is not None:
            return revision
        self.refresh_cache()
        return self.try_get_by_environment(environment_id, version)

    def refresh_cache(self):
        logger.info("Refreshing EnvironmentRevision cache.")
        self.cache = {}
        for revision in MONGO_DATABASE.get_collection(
            "environment_revisions"
        ).find():
            self.cache[revision["_id"]] = EnvironmentRevision(revision)
        logger.info(f"Found {len(self.cache)} environment revisions.")

class Project:
    def __init__(self, project: dict):
        self._id = ObjectId(project["_id"])
        self.environment_id = project["overrideV2EnvironmentId"]
        self.default_environment_revision_spec = project["defaultEnvironmentRevisionSpec"]




class ProjectsCache:
    def __init__(self):
        logger.info("Initializing Project cache.")
        self.cache: Dict[ObjectId, Project] = {}

    def get(
        self, project_id: ObjectId
    ) -> Optional[Project]:
        if project_id not in self.cache:
            self.refresh_cache()
        return self.cache.get(project_id)

    def try_get_by_project(
        self, project_id: ObjectId
    ) -> Optional[Project]:
        for project in self.cache.values():
            if (
                str(project._id) == str(project_id)
            ):
                return project
        return None

    def get_by_project(
        self, project_id: ObjectId
    ) -> Optional[Project]:
        project = self.try_get_by_project(project_id)
        if project is not None:
            return project
        self.refresh_cache()
        return self.try_get_by_project(project_id)

    def refresh_cache(self):
        logger.info("Refreshing Project cache.")
        self.cache = {}
        for project in MONGO_DATABASE.get_collection(
            "projects"
        ).find():
            self.cache[project["_id"]] = Project(project)
        logger.info(f"Found {len(self.cache)} projects.")


ENVIRONMENT_REVISION_CACHE = EnvironmentRevisionCache()
PROJECTS_CACHE = ProjectsCache()
MONGO_DATABASE = create_database_connection()
if __name__ == "__main__":
    if len(sys.argv) > 1:
        DOMINO_NUCLEUS_URI: str = sys.argv[1]

    lvl = logging.getLevelName(os.environ.get("LOG_LEVEL", "WARNING"))
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    log = logging.getLogger("extendedapi_server")
    log.setLevel(logging.WARNING)

    logger.warning(MONGO_DATABASE.client)
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=5000,
        debug=debug,
        #ssl_context=("/ssl/tls.crt", "/ssl/tls.key"),
    )
    MONGO_DATABASE.client.close()