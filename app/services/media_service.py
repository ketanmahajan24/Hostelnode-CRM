import os
import uuid
import aiofiles
from fastapi import UploadFile
from app.config import settings


async def save_upload(file: UploadFile) -> dict:
    """Saves an uploaded file to disk and returns metadata for referencing it later."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(settings.upload_dir, unique_name)

    async with aiofiles.open(full_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):
            await out_file.write(chunk)

    return {
        "filename": file.filename,
        "stored_path": full_path,
        "url": f"/{full_path}",
        "mime_type": file.content_type,
    }


async def save_inbound_media(content: bytes, mime_type: str, suggested_name: str | None = None) -> dict:
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = _ext_from_mime(mime_type)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(settings.upload_dir, unique_name)
    async with aiofiles.open(full_path, "wb") as out_file:
        await out_file.write(content)
    return {
        "filename": suggested_name or unique_name,
        "stored_path": full_path,
        "url": f"/{full_path}",
        "mime_type": mime_type,
    }


def _ext_from_mime(mime_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "video/mp4": ".mp4", "video/3gpp": ".3gp",
        "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/amr": ".amr", "audio/aac": ".aac",
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }
    return mapping.get(mime_type, "")
