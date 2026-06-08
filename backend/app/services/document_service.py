from fastapi import UploadFile
from pathlib import Path
import shutil
import uuid
import aiofiles


async def save_upload(file: UploadFile, dest_dir: Path):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = dest_dir / filename

    # stream write
    async with aiofiles.open(dest_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)

    metadata = {
        "filename": file.filename,
        "content_type": file.content_type,
        "meta": {},
        "source": "upload",
    }
    return dest_path, metadata
