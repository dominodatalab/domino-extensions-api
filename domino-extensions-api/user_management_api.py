

from flask import request, jsonify, Blueprint, Response  # type: ignore
import logging
import requests
import os
from datetime import datetime, timedelta
from mongo import create_database_connection
from keycloak_utils import  create_keycloak_connection
import utils

ROLE_SYSADMIN = "SysAdmin"
ROLE_LICENSE_REVIEWER = "LicenseReviewer"
ROLE_SUPPORT_STAFF = "SupportStaff"
ROLE_LIMITED_ADMIN = "LimitedAdmin"
ROLE_PRACTIONER = "Practitioner"
ROLE_PROJECT_MANAGER = "ProjectManager"
ROLE_LIBRARIAN = "Librarian"
ROLE_READ_ONLY_SUPPORT_STAFF = "ReadOnlySupportStaff"
ALL_ROLES = [ROLE_SYSADMIN,ROLE_LICENSE_REVIEWER,ROLE_SUPPORT_STAFF,
             ROLE_LIMITED_ADMIN,ROLE_PRACTIONER,ROLE_PROJECT_MANAGER,ROLE_LIBRARIAN,ROLE_READ_ONLY_SUPPORT_STAFF]

user_management_api = Blueprint("user_management_api", __name__)
MONGO_DATABASE = create_database_connection()
KEYCLOAK = create_keycloak_connection()
DOMINO_API_HOST='http://nucleus-frontend.domino-platform:80'
domino_version = requests.get(f"{DOMINO_API_HOST}/version").json()['version']

lindex = domino_version.rfind('.')
major_minor_version = float(domino_version[0:lindex])
print('Domino Version : ' + str(domino_version))

print('Domino Major/Minor Version : ' + str(major_minor_version))


lvl: str = logging.getLevelName(os.environ.get("LOG_LEVEL", "WARNING"))
logging.basicConfig(
    level=lvl,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("domino-extension-api-user-management")
logger.setLevel(logging.WARNING)
DEFAULT_PLATFORM_NAMESPACE = "domino-platform"



def are_roles_valid(roles):
    if len(roles) >0:
        for r in roles:
            if r not in ALL_ROLES:
                return False
    return True



def _get_group_id_by_name(groups):
    group_id_by_name={}
    for g in groups:
        group_id_by_name[g['name']]=g['id']
    return group_id_by_name

def _is_user_in_group(role_name,user_groups):
    for g in user_groups:
        if g['name']==role_name:
            return True
    return False


@user_management_api.route("/user-management/roles/<user_name>", methods=["POST"])
def update_roles(user_name) -> object:
    if major_minor_version < 5.6:
        return jsonify({}), 403

    current_roles = []
    new_roles = []
    try:
        payload = request.json
        new_roles = payload['roles']
        if are_roles_valid(new_roles):
            if utils.is_user_authorized(utils.get_headers(request.headers)):
                keycloak = create_keycloak_connection()
                kc_groups = []
                for g in keycloak.get_groups():
                    if g['name'] == 'roles':
                        kc_groups = g['subGroups']
                group_id_by_name = _get_group_id_by_name(kc_groups)
                user_id = keycloak.get_user_id(user_name)
                user_groups = keycloak.get_user_groups(user_id)
                user = MONGO_DATABASE.get_collection("users").find_one(filter={'loginId.id': user_name})

                if user:
                    current_roles = user['_systemRoles']
                user['_systemRoles'] = new_roles

                #Only update keycloak group membership for 5.7 and above
                if major_minor_version>5.6:
                    # Remove group memberships
                    for r in current_roles:
                        if r not in new_roles and \
                                _is_user_in_group(r, user_groups):
                            group_id = group_id_by_name[r]
                            logger.warning(f'Removing role {r} from user {user_name}')
                            keycloak.group_user_remove(user_id, group_id)

                    # Add group memberships
                    for r in new_roles:
                        if r not in current_roles:
                            group_id = group_id_by_name[r]
                            logger.warning(f'Adding role {r} for user {user_name}')
                            keycloak.group_user_add(user_id, group_id)

                users_collection = MONGO_DATABASE.get_collection('users')

                query = {"_id": user["_id"]}
                users_collection.update_one(query, {"$set": user}, upsert=True)
                json = {'user_name': user_name, 'current_roles': current_roles, 'current_roles': new_roles,
                        'message': f"Success : Roles updated "}
                return jsonify(json), 200
            else:
                json = {"message": f"Unauthorized to list user roles because not an admin"}
                return jsonify(json), 403
        else:
            json = {'roles': new_roles, 'Message': 'Error One of the roles is invalid. Must be empty or each element '+
                                                        'one of ' + ','.join(ALL_ROLES)}
            return jsonify(json), 500
    except Exception as e:
        logger.exception(e)
        logger.warning(
            f"Error Updating roles for the User {user_name}"
        )
        message = str(e)
        json = {'user_name':user_name, 'current_roles':current_roles, 'current_roles':new_roles, 'message' : f"Error : {message}"}
        return jsonify(json), 500


def get_keycloak_ids(users):
    ids_to_delete = []
    users_collection = MONGO_DATABASE['users'].find()
    for user in users_collection:
        id = user['_id']
        idp_id = user['idpId']
        login_id = user['loginId']['id']
        if login_id in users:
            ids_to_delete.append(idp_id)
    return ids_to_delete


@user_management_api.route("/user-management/inactivefor/<days>", methods=["GET"])
def get_inactive_users(days) -> object:

    try:
        if utils.is_user_authorized(utils.get_headers(request.headers)):
            # for collection in collections:
            #    print(collection)
            collections = MONGO_DATABASE.list_collection_names()
            users_collection = MONGO_DATABASE['users'].find()

            days_ago = datetime.utcnow() - timedelta(days=int(days))

            # Convert to ISO 8601 format
            days_ago_iso = days_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
            days_ago_iso = days_ago_iso.replace("Z", "+00:00")
            query = {"queued": {"$gt":  datetime.fromisoformat(days_ago_iso)}}
            runs_collection = MONGO_DATABASE['runs'].find(query)

            service_accounts_idp_ids = []
            if 'service_account_tokens' in collections:
                service_accounts_tokens_collection = MONGO_DATABASE['service_account_tokens'].find()
                for s in service_accounts_tokens_collection:
                    if s['serviceAccountIdpId'] not in service_accounts_idp_ids:
                        service_accounts_idp_ids.append(s['serviceAccountIdpId'])



            users_by_id = {}
            service_accounts_by_id = {}
            service_accounts = []
            # Maintaining distinction between users and service accounts in if condition just in case
            for user in users_collection:
                id = user['_id']
                idp_id = user['idpId']
                login_id = user['loginId']['id']
                users_by_id[id] = login_id
                if idp_id not in service_accounts_idp_ids:
                    print(f'Regular user {login_id}')
                    users_by_id[id] = login_id
                else:
                    print(f'Svc account {login_id}')
                    users_by_id[id] = login_id
                    service_accounts.append(login_id)


            active_users = []
            for r in runs_collection:
                startingUserId = r['startingUserId']
                user_id = users_by_id[startingUserId]
                active_users.append(user_id)

            inactive_users = []

            for key, value in users_by_id.items():
                if value not in active_users:
                    is_svc_account=False
                    if value in  service_accounts:
                        is_svc_account = True
                    inactive_users.append({'user_name':value,'is_svc_account':is_svc_account})

            json = {'inactive_accounts': inactive_users}
            return jsonify(json),200
    except Exception as e:
        logger.exception(e)
        logger.warning(
            f"Error fetching inactive users"
        )
        message = str(e)
        json = {"message":message}
        return jsonify(json), 500

@user_management_api.route("/user-management/deactivate", methods=["POST"])
def deactivate() -> object:
    payload = request.json
    if utils.is_user_authorized(utils.get_headers(request.headers)):
        return change_activation_status(payload['users'],False)
    else:
        json = {'message': 'Only Admins are authorized to make this call'}
        return jsonify(json), 403

@user_management_api.route("/user-management/activate", methods=["POST"])
def activate() -> object:
    payload = request.json
    if utils.is_user_authorized(utils.get_headers(request.headers)):
        return change_activation_status(payload['users'],True)
    else:
        json = {'message': 'Only Admins are authorized to make this call'}
        return jsonify(json), 403

def change_activation_status(users,status:bool):
    updated_users = []
    try:
        if utils.is_user_authorized(utils.get_headers(request.headers)):
            keycloak = create_keycloak_connection()
            ids = get_keycloak_ids(users)
            for id in ids:
                user = keycloak.get_user(id)
                # Update user status
                user['enabled'] = status
                keycloak.update_user(user_id=id, payload=user)
                username = user['username']
                updated_users.append(username)

    except Exception as e:
        logger.exception(e)
        result = ','.join(updated_users)
        logger.warning(
            f"Error updating activation status of users. Some users may be updated {result}"
        )
        message = str(e)
        json = {'updated_users':updated_users,'message' : f"Error : {message}"}
        return jsonify(json), 500
    result = ','.join(updated_users)
    print('Updated users ' + result)
    json = {'updated_users': updated_users}
    return jsonify(json), 200
def get_keycloak_ids(users):
    ids_to_delete = []
    users_collection = MONGO_DATABASE['users'].find()
    for user in users_collection:
        id = user['_id']
        idp_id = user['idpId']
        login_id = user['loginId']['id']
        if login_id in users:
            ids_to_delete.append(idp_id)
    return ids_to_delete