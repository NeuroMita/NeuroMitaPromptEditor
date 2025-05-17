from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm # Handles username/password form data
from datetime import timedelta

from app.models.user import Token, UserLogin, UserCreate, User # Добавили UserCreate, User
from app.auth import authenticate_user, add_user_to_db, get_user # Добавили add_user_to_db, get_user
from app.utils.security import create_access_token
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, INVITE_CODE # Добавили INVITE_CODE
from app.utils.logger_api import api_logger

router = APIRouter()

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    api_logger.info(f"Login attempt for user: {form_data.username}")
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        api_logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    api_logger.info(f"User {form_data.username} logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=User)
async def register_new_user(user_data: UserCreate):
    api_logger.info(f"Registration attempt for username: {user_data.username}")

    if user_data.invite_code != INVITE_CODE:
        api_logger.warning(f"Invalid invite code provided by {user_data.username} for registration.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invite code.",
        )

    existing_user = get_user(user_data.username)
    if existing_user:
        api_logger.warning(f"Registration attempt for existing username: {user_data.username}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered.",
        )

    try:
        new_user_in_db = add_user_to_db(username=user_data.username, password=user_data.password)

        if not new_user_in_db:
            api_logger.error(f"User creation failed for {user_data.username} without explicit exception in add_user_to_db.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User registration failed unexpectedly (internal check).")

        api_logger.info(f"User {user_data.username} registered successfully.")
        return User(**new_user_in_db.model_dump())
    except Exception as e:
        api_logger.error(f"Error during registration process for {user_data.username}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during registration: {str(e)}",
        )