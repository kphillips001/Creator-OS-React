"""Bounded preparation of private customer media; deliberately no vision."""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageOps, UnidentifiedImageError

from app.repositories.telegram_inbound_media_repository import TelegramInboundMediaRepository

class UnsupportedCustomerImageError(ValueError):
    pass


class TelegramInboundMediaService:
    SUPPORTED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
    SUPPORTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

    def __init__(self, *, repository=None, maximum_bytes=None, maximum_pixels=None,
                 maximum_dimension=None, timeout_seconds=None, storage_root=None,
                 logger=None):
        self.repository=repository or TelegramInboundMediaRepository()
        self.maximum_bytes=int(maximum_bytes or os.getenv("TELEGRAM_CUSTOMER_MEDIA_MAX_BYTES",10*1024*1024))
        self.maximum_pixels=int(maximum_pixels or os.getenv("TELEGRAM_CUSTOMER_MEDIA_MAX_PIXELS",40_000_000))
        self.maximum_dimension=int(maximum_dimension or os.getenv("TELEGRAM_CUSTOMER_MEDIA_MAX_DIMENSION",12_000))
        self.timeout_seconds=float(timeout_seconds or os.getenv("TELEGRAM_CUSTOMER_MEDIA_DOWNLOAD_TIMEOUT_SECONDS",20))
        self.storage_root=Path(storage_root or os.getenv("TELEGRAM_CUSTOMER_MEDIA_TEMP_DIR") or (Path(tempfile.gettempdir())/"creator_os_customer_media"))
        self.logger=logger or logging.getLogger("telegram-inbound-media")

    async def process(self, *, creator_profile_id, fanvue_account_id, payload, downloader):
        operation=await asyncio.to_thread(self.repository.receive,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,payload=payload)
        rows=await asyncio.to_thread(self.repository.attachments,operation["operation_id"])
        source={item.attachment_id:item for item in payload.attachments}
        for row in rows:
            if row["state"] in self.repository.TERMINAL:
                continue
            attachment=source.get(str(row["attachment_id"])) or SimpleNamespace(
                attachment_id=str(row["attachment_id"]),telegram_message_id=row["telegram_message_id"],
                telegram_chat_id=operation["telegram_chat_id"],telegram_user_id=operation["telegram_user_id"],
            )
            await self._process_attachment(row,attachment,downloader)
        return await asyncio.to_thread(self.repository.refresh_operation,operation["operation_id"])

    async def _process_attachment(self,row,attachment,downloader):
        attachment_id=row["attachment_id"]
        if row["state"]=="VALIDATED" and row.get("normalized_path") and Path(row["normalized_path"]).is_file():
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"READY_FOR_ANALYSIS",ready_at=datetime.now(timezone.utc))
        mime=str(row.get("telegram_mime_type") or "").lower()
        if row["media_kind"]=="IMAGE_DOCUMENT" and mime not in self.SUPPORTED_MIME_TYPES:
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"UNSUPPORTED",failure_category="UNSUPPORTED_TELEGRAM_MIME")
        reported=row.get("reported_size_bytes")
        if reported is not None and int(reported)>self.maximum_bytes:
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"OVERSIZED",failure_category="REPORTED_SIZE_LIMIT")
        await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"DOWNLOADING")
        try:
            data=await downloader(attachment,maximum_bytes=self.maximum_bytes,timeout_seconds=self.timeout_seconds)
        except asyncio.TimeoutError:
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"DOWNLOAD_FAILED",failure_category="DOWNLOAD_TIMEOUT")
        except ValueError as error:
            state="OVERSIZED" if "size" in str(error).lower() else "DOWNLOAD_FAILED"
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,state,failure_category="ACTUAL_SIZE_LIMIT" if state=="OVERSIZED" else "DOWNLOAD_REJECTED")
        except (FileNotFoundError,OSError):
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"DOWNLOAD_FAILED",failure_category="MEDIA_UNAVAILABLE")
        if len(data)>self.maximum_bytes:
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"OVERSIZED",failure_category="ACTUAL_SIZE_LIMIT")
        await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"DOWNLOADED",actual_size_bytes=len(data),downloaded_at=datetime.now(timezone.utc))
        try:
            artifact=self._validate_and_store(bytes(data),str(attachment_id))
        except UnsupportedCustomerImageError:
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"UNSUPPORTED",failure_category="UNSUPPORTED_DECODED_FORMAT")
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
            return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"DECODE_FAILED",failure_category="IMAGE_DECODE_OR_LIMIT_FAILED")
        await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"VALIDATED",**artifact,validated_at=datetime.now(timezone.utc))
        return await asyncio.to_thread(self.repository.transition_attachment,attachment_id,"READY_FOR_ANALYSIS",ready_at=datetime.now(timezone.utc))

    def _validate_and_store(self,data,attachment_id):
        Image.MAX_IMAGE_PIXELS=self.maximum_pixels
        with Image.open(io.BytesIO(data)) as opened:
            detected=str(opened.format or "").upper()
            if detected not in self.SUPPORTED_FORMATS:
                raise UnsupportedCustomerImageError("unsupported decoded format")
            opened.verify()
        with Image.open(io.BytesIO(data)) as opened:
            width,height=opened.size
            if width<=0 or height<=0 or width>self.maximum_dimension or height>self.maximum_dimension or width*height>self.maximum_pixels:
                raise ValueError("decoded dimensions exceed configured limit")
            normalized=ImageOps.exif_transpose(opened).convert("RGB")
            self.storage_root.mkdir(parents=True,exist_ok=True)
            destination=self.storage_root/f"{attachment_id}.jpg"
            handle=tempfile.NamedTemporaryFile(dir=self.storage_root,suffix=".tmp",delete=False)
            temporary=Path(handle.name);handle.close()
            try:
                # A fresh JPEG pixel encoding intentionally carries no EXIF, GPS,
                # camera serial, device identifier, comments, or source profile.
                normalized.save(temporary,"JPEG",quality=90,optimize=True,exif=b"")
                os.replace(temporary,destination)
            finally:
                temporary.unlink(missing_ok=True);normalized.close()
        return {"detected_format":detected,"detected_mime_type":f"image/{'jpeg' if detected=='JPEG' else detected.lower()}","decoded_width":width,"decoded_height":height,"normalized_path":str(destination),"content_sha256":hashlib.sha256(data).hexdigest()}

    def cleanup_expired(self):
        removed=0
        for row in self.repository.expired_artifacts():
            path=Path(str(row.get("normalized_path") or ""))
            try:
                resolved=path.resolve();root=self.storage_root.resolve()
                if resolved.parent==root:
                    resolved.unlink(missing_ok=True);removed+=1
                self.repository.clear_artifact(row["attachment_id"])
            except OSError:
                self.logger.warning("event=telegram_media_cleanup status=failure attachment_id=%s",str(row["attachment_id"])[:8])
        return removed
