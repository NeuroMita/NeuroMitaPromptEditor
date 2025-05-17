import json
from pathlib import Path
from typing import Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import USER_DATA_FILE, USER_PROMPTS_ROOT_PATH
from app.models.user import User, UserInDB, TokenData
from app.utils.security import verify_password, decode_access_token, get_password_hash
from app.utils.logger_api import api_logger

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

_users_db: Dict[str, UserInDB] = {}

def load_users_from_file():
    global _users_db
    _users_db = {}
    if USER_DATA_FILE.exists():
        try:
            with open(USER_DATA_FILE, "r") as f:
                users_data_raw = json.load(f)
            for username, user_data in users_data_raw.items():
                _users_db[username] = UserInDB(**user_data)
            api_logger.info(f"Loaded {len(_users_db)} users from {USER_DATA_FILE}")
        except json.JSONDecodeError:
            api_logger.error(f"Error decoding JSON from {USER_DATA_FILE}. User database is empty.")
        except Exception as e:
            api_logger.error(f"Failed to load users from {USER_DATA_FILE}: {e}. User database is empty.")
    else:
        api_logger.warning(f"User data file {USER_DATA_FILE} not found. User database is empty.")
        # Create an empty file if it doesn't exist to avoid errors on first save
        try:
            USER_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(USER_DATA_FILE, "w") as f:
                json.dump({}, f)
            api_logger.info(f"Created empty user data file: {USER_DATA_FILE}")
        except Exception as e:
            api_logger.error(f"Could not create empty user data file {USER_DATA_FILE}: {e}")


def save_user_to_file(user: UserInDB):
    """Saves or updates a single user in the JSON file."""
    global _users_db
    _users_db[user.username] = user # Update in-memory cache
    
    # Prepare data for JSON serialization (Path objects are not directly serializable)
    users_to_save = {}
    for uname, u_obj in _users_db.items():
        users_to_save[uname] = u_obj.model_dump() # Pydantic V2

    try:
        USER_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USER_DATA_FILE, "w") as f:
            json.dump(users_to_save, f, indent=4)
        api_logger.info(f"User {user.username} saved to {USER_DATA_FILE}")
    except Exception as e:
        api_logger.error(f"Failed to save user {user.username} to {USER_DATA_FILE}: {e}")
        # Potentially roll back in-memory change or handle error appropriately
        # For now, we'll log and continue, but this could lead to inconsistency
        # if the file save fails after an in-memory update.


def get_user(username: str) -> Optional[UserInDB]:
    return _users_db.get(username)

def authenticate_user(username: str, password: str) -> Optional[User]:
    user_in_db = get_user(username)
    if not user_in_db:
        return None
    if not verify_password(password, user_in_db.hashed_password):
        return None
    return User(**user_in_db.model_dump())


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    username: str | None = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    user = get_user(username)
    if user is None:
        raise credentials_exception
    
    # Construct the full prompts_path for the user object at runtime
    # This is a good place to ensure the user's prompt directory exists
    user_prompts_abs_path = USER_PROMPTS_ROOT_PATH / user.prompts_dir_relative
    user_prompts_abs_path.mkdir(parents=True, exist_ok=True)
    
    # We return a User model instance, not UserInDB directly from _users_db,
    # to allow for potential transformations or additional runtime fields.
    return User(**user.model_dump())


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    # if current_user.disabled: # If you add a 'disabled' field to User model
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# Call load_users_from_file() when this module is imported so _users_db is populated.
load_users_from_file()

# Helper function to add a user (e.g., for initial setup or admin script)
def add_user_to_db(username: str, password: str, is_admin: bool = False): # is_admin param not used by registration endpoint
    """
    Adds a new user to the users.json file.
    The user's prompt directory will be relative to USER_PROMPTS_ROOT_PATH.
    Example: USER_PROMPTS_ROOT_PATH / username
    Raises Exception if directory creation fails.
    Returns UserInDB object if successful, or None if user already exists (though this check is usually done before calling).
    """
    if get_user(username):
        api_logger.warning(f"User {username} already exists. Not adding (should be checked before calling).")
        return None

    hashed_password = get_password_hash(password)
    # User's prompt directory will be their username by default
    user_prompts_dir_relative = username 
    
    user_data = {
        "username": username,
        "hashed_password": hashed_password,
        "prompts_dir_relative": user_prompts_dir_relative,
        # "is_admin": is_admin, # Example of an additional field
    }
    new_user_in_db_model = UserInDB(**user_data)
    
    # Ensure the user's personal prompts directory exists
    user_specific_prompts_path = USER_PROMPTS_ROOT_PATH / new_user_in_db_model.prompts_dir_relative
    try:
        user_specific_prompts_path.mkdir(parents=True, exist_ok=True)
        api_logger.info(f"Ensured user prompt directory exists: {user_specific_prompts_path}")
    except Exception as e:
        api_logger.error(f"Could not create directory {user_specific_prompts_path} for user {username}: {e}")
        # Re-raise to allow the calling API endpoint to handle it (e.g., return 500)
        raise Exception(f"Failed to create user directory for {username}") from e

    save_user_to_file(new_user_in_db_model)
    api_logger.info(f"User {username} added to database.")
    return new_user_in_db_model