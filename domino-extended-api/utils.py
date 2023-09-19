
import os
import sys
import requests
from typing import Dict, Optional
import logging

logger = logging.getLogger("extended-api")

WHO_AM_I_ENDPOINT = "v4/auth/principal"
DOMINO_NUCLEUS_URI = "http://nucleus-frontend.domino-platform:80"

def get_headers(headers):
    new_headers = {}
    if 'X-Domino-Api-Key' in headers:
        new_headers['X-Domino-Api-Key'] = headers['X-Domino-Api-Key']
    elif 'Authorization' in headers:
        new_headers['Authorization'] = headers['Authorization']
    return new_headers


def is_user_authorized(headers):
    url: str = os.path.join(DOMINO_NUCLEUS_URI, WHO_AM_I_ENDPOINT)
    ret: Dict = requests.get(url, headers=headers)
    if ret.status_code == 200:
        user: str = ret.json()
        user_name: str = user["canonicalName"]
        logger.warning(f'Extended API Invoking User {user_name}')
        is_admin: bool = user["isAdmin"]
        if is_admin:  # Admins can update mutations
            logger.warning(f"User {user_name} allowed because user is a Domino Admin")
            return True
        else:
            return False
    else:
        raise Exception(str(ret.status_code) + " - Error getting user status")