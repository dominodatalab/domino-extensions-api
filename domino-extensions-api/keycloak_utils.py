
import logging
import os


from domino_creds import DominoSystemCred, KeyCloakDetails
from keycloak import KeycloakAdmin

logger = logging.getLogger(__name__)
DEFAULT_PLATFORM_NAMESPACE = "domino-platform"
logger = logging.getLogger(__name__)


def create_keycloak_connection():
    keycloak_server = f'http://keycloak-http.domino-platform.svc.cluster.local/auth/'
    domino_system_cred = DominoSystemCred()
    keycloak_details = KeyCloakDetails(domino_system_cred)
    username = keycloak_details.keycloak_username
    password = keycloak_details.keycloak_password
    admin_connection = KeycloakAdmin(
        server_url=keycloak_server,
        username=username,
        password=password,
        realm_name="DominoRealm",
        user_realm_name="master"
    )
    print('Keycloak connection established')
    return admin_connection