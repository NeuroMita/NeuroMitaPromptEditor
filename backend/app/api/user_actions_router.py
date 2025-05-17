# backend/app/api/user_actions_router.py
import io
import zipfile
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, status

from app.core.config import USER_PROMPTS_ROOT_PATH
from app.auth import User, get_current_active_user
from app.utils.logger_api import api_logger
from app.utils.file_utils import check_user_quota, get_directory_size # Import quota utils
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.get("/prompts/download", response_class=StreamingResponse)
async def download_user_prompts_zip(current_user: User = Depends(get_current_active_user)):
    """
    Downloads all prompts for the current user as a ZIP archive.
    Returns 204 No Content if the user's prompts directory is empty or contains no files.
    """
    user_prompts_dir = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' initiated download for prompts from '{user_prompts_dir}'.")

    if not user_prompts_dir.is_dir():
        api_logger.warning(f"User '{current_user.username}' prompts directory '{user_prompts_dir}' not found for download.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompts directory not found.")

    zip_buffer = io.BytesIO()
    files_added_to_zip = False
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file_obj:
        for item in user_prompts_dir.rglob('*'):
            if item.is_file():
                arcname = item.relative_to(user_prompts_dir)
                zip_file_obj.write(item, arcname=arcname)
                files_added_to_zip = True
                api_logger.debug(f"Added to ZIP for user '{current_user.username}': {arcname}")

    if not files_added_to_zip:
        api_logger.info(f"User '{current_user.username}' prompts directory '{user_prompts_dir}' is empty. No files to download.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    zip_buffer.seek(0)
    
    filename = f"{current_user.username}_prompts.zip"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\""
    }
    api_logger.info(f"Sending ZIP archive '{filename}' to user '{current_user.username}'.")
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


@router.post("/prompts/upload-zip")
async def upload_user_prompts_zip(
    current_user: User = Depends(get_current_active_user),
    file: UploadFile = File(...)
):
    """
    Uploads a ZIP archive and extracts its contents into the user's prompts directory.
    Existing files with the same name will be overwritten.
    Checks user quota before extraction.
    """
    user_prompts_dir = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' initiated ZIP upload to '{user_prompts_dir}'. Filename: '{file.filename}'.")

    user_prompts_dir.mkdir(parents=True, exist_ok=True)

    if not file.filename.lower().endswith(".zip"):
        api_logger.warning(f"User '{current_user.username}' uploaded non-ZIP file: '{file.filename}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type. Please upload a .zip file.")

    zip_content_bytes = await file.read()
    
    try:
        if not zipfile.is_zipfile(io.BytesIO(zip_content_bytes)):
            api_logger.warning(f"User '{current_user.username}' uploaded invalid ZIP file: '{file.filename}'. is_zipfile check failed.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is not a valid ZIP archive.")
    except Exception as e:
        api_logger.error(f"Error during is_zipfile check for '{file.filename}' by user '{current_user.username}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error validating ZIP file: {e}")

    # --- Quota Check ---
    estimated_size_increase_bytes = 0
    member_infos_for_extraction = [] # Store valid member_info and target_path

    try:
        with zipfile.ZipFile(io.BytesIO(zip_content_bytes), "r") as zip_f:
            for member_info in zip_f.infolist():
                member_path_str = member_info.filename
                relative_member_path = Path(member_path_str)
                target_path = (user_prompts_dir / relative_member_path).resolve()

                # Security check for path traversal
                if not str(target_path).startswith(str(user_prompts_dir.resolve())):
                    api_logger.warning(
                        f"Path traversal attempt by user '{current_user.username}' with ZIP path '{member_path_str}'. "
                        f"Resolved to '{target_path}' which is outside '{user_prompts_dir.resolve()}'."
                    )
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid path in ZIP: '{member_path_str}' leads outside designated user area.")
                
                member_infos_for_extraction.append({"info": member_info, "target_path": target_path})

                if not member_info.is_dir():
                    size_of_file_in_zip = member_info.file_size
                    current_size_on_disk = 0
                    if target_path.is_file():
                        try:
                            current_size_on_disk = target_path.stat().st_size
                        except FileNotFoundError: # File might be listed in ZIP but not exist yet, or deleted during this check.
                            pass
                    
                    delta_for_this_file = size_of_file_in_zip - current_size_on_disk
                    estimated_size_increase_bytes += delta_for_this_file
        
        # Perform the actual quota check
        check_user_quota(user_prompts_dir, current_user.username, additional_size_bytes=estimated_size_increase_bytes)

    except HTTPException as e: # Catch quota or path traversal HTTPException
        raise e
    except zipfile.BadZipFile:
        api_logger.warning(f"User '{current_user.username}' uploaded a bad ZIP file during pre-check: '{file.filename}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad ZIP file identified during pre-extraction checks.")
    except Exception as e:
        api_logger.error(f"Unexpected error during ZIP pre-check/quota calculation for user '{current_user.username}', file '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error during pre-extraction analysis: {e}")
    # --- End Quota Check ---


    # --- Actual Extraction ---
    extracted_count = 0
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content_bytes), "r") as zip_f:
            for item in member_infos_for_extraction: # Use the validated list
                member_info = item["info"]
                target_path: Path = item["target_path"]

                if member_info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    api_logger.debug(f"Created/ensured directory from ZIP for user '{current_user.username}': {target_path}")
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True) # Ensure parent dir exists
                    with target_path.open("wb") as f_out:
                        with zip_f.open(member_info, "r") as f_in: # Open member_info directly from zip_f
                            shutil.copyfileobj(f_in, f_out)
                    extracted_count += 1
                    api_logger.debug(f"Extracted file from ZIP for user '{current_user.username}': {target_path}")
    except zipfile.BadZipFile: # Should be caught by pre-check, but as a fallback
        api_logger.warning(f"User '{current_user.username}' uploaded a bad ZIP file: '{file.filename}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad ZIP file.")
    except Exception as e:
        api_logger.error(f"Error extracting ZIP for user '{current_user.username}', file '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error extracting ZIP file: {e}")
    
    api_logger.info(f"Successfully extracted {extracted_count} files from ZIP for user '{current_user.username}' to '{user_prompts_dir}'.")
    return {"message": f"ZIP file imported successfully. {extracted_count} file(s) extracted."}