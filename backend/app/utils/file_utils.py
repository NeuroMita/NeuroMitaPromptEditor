# backend/app/utils/file_utils.py
from pathlib import Path
from fastapi import HTTPException, status
from app.core.config import USER_QUOTA_MB # Import the quota limit
from app.utils.logger_api import api_logger # For logging quota checks

def get_directory_size(directory_path: Path) -> int:
    """Calculates the total size of all files in a directory and its subdirectories."""
    total_size = 0
    if not directory_path.is_dir():
        return 0
    for item in directory_path.rglob('*'):
        if item.is_file():
            try:
                total_size += item.stat().st_size
            except FileNotFoundError:
                # File might have been deleted between rglob and stat, skip it
                api_logger.warning(f"File {item} not found during size calculation, skipping.")
                continue
    return total_size

def check_user_quota(
    user_prompts_dir: Path,
    current_user_username: str, # For logging purposes
    additional_size_bytes: int = 0
):
    """
    Checks if the user's current prompt directory size plus any additional
    bytes will exceed the defined quota.
    Raises HTTPException with status 413 if quota is exceeded.
    """
    current_size_bytes = get_directory_size(user_prompts_dir)
    potential_new_size_bytes = current_size_bytes + additional_size_bytes
    quota_bytes = USER_QUOTA_MB * 1024 * 1024

    api_logger.debug(
        f"Quota check for user '{current_user_username}': "
        f"Current size: {current_size_bytes / (1024*1024):.2f}MB, "
        f"Additional: {additional_size_bytes / (1024*1024):.2f}MB, "
        f"Potential new: {potential_new_size_bytes / (1024*1024):.2f}MB, "
        f"Quota: {USER_QUOTA_MB:.2f}MB"
    )

    if potential_new_size_bytes > quota_bytes:
        exceeded_by_mb = (potential_new_size_bytes - quota_bytes) / (1024 * 1024)
        error_detail = (
            f"User quota of {USER_QUOTA_MB}MB exceeded. "
            f"Operation would result in usage of {potential_new_size_bytes / (1024*1024):.2f}MB "
            f"(exceeding by {exceeded_by_mb:.2f}MB). "
            f"Please free up space or contact admin."
        )
        api_logger.warning(
            f"Quota exceeded for user '{current_user_username}'. Details: {error_detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, # Correct status code for payload too large / quota
            detail=error_detail
        )
    api_logger.debug(f"Quota check passed for user '{current_user_username}'.")