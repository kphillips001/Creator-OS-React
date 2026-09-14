import io
import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from app.models.telegram_inbound import TelegramInboundAttachment, TelegramInboundPayload
from app.services.telegram_inbound_media_service import TelegramInboundMediaService


class Repository:
    TERMINAL={"READY_FOR_ANALYSIS","UNSUPPORTED","OVERSIZED","DOWNLOAD_FAILED","DECODE_FAILED","FAILED"}
    def __init__(self): self.rows={};self.operation={"operation_id":uuid4(),"telegram_chat_id":2,"telegram_user_id":1}
    def receive(self,**values):
        for a in values["payload"].attachments:
            self.rows.setdefault(a.attachment_id,{"attachment_id":a.attachment_id,"operation_id":self.operation["operation_id"],"telegram_message_id":a.telegram_message_id,"telegram_media_id":a.telegram_media_id,"media_kind":a.media_kind,"telegram_mime_type":a.mime_type,"reported_size_bytes":a.reported_size_bytes,"state":"RECEIVED"})
        return self.operation
    def attachments(self,_): return list(self.rows.values())
    def transition_attachment(self,key,state,**values): self.rows[str(key)].update(state=state,**values);return self.rows[str(key)]
    def refresh_operation(self,_,**kwargs):
        states=[r["state"] for r in self.rows.values()];self.operation["state"]="READY_FOR_ANALYSIS" if any(s=="READY_FOR_ANALYSIS" for s in states) else "FAILED";return self.operation
    def expired_artifacts(self): return []
    def clear_artifact(self,_): pass


def image_bytes(kind="JPEG",size=(20,10)):
    stream=io.BytesIO();Image.new("RGB",size,"red").save(stream,kind);return stream.getvalue()

def rotated_jpeg():
    stream=io.BytesIO();image=Image.new("RGB",(20,10),"red");exif=Image.Exif();exif[274]=6;image.save(stream,"JPEG",exif=exif);return stream.getvalue()

def gps_jpeg():
    stream=io.BytesIO();image=Image.new("RGB",(20,10),"red");exif=Image.Exif()
    exif[271]="PRIVATE-CAMERA";exif[272]="PRIVATE-DEVICE";exif[42033]="SERIAL-123"
    image.save(stream,"JPEG",exif=exif);return stream.getvalue()

def payload(*attachments,text=""):
    return TelegramInboundPayload(telegram_user_id=1,telegram_chat_id=2,message_text=text,message_id=attachments[0].telegram_message_id,attachments=tuple(attachments))

def attachment(message=3,**changes):
    values=dict(attachment_id=str(uuid4()),telegram_message_id=message,telegram_chat_id=2,telegram_user_id=1,media_kind="PHOTO",telegram_media_id=str(message),mime_type="image/jpeg")
    values.update(changes);return TelegramInboundAttachment(**values)

def test_valid_media_only_jpeg_reaches_ready_without_fake_text_or_provider(tmp_path):
    repo=Repository();service=TelegramInboundMediaService(repository=repo,storage_root=tmp_path)
    calls=[]
    async def download(item,**limits): calls.append((item,limits));return image_bytes()
    result=asyncio.run(service.process(creator_profile_id=1,fanvue_account_id=2,payload=payload(attachment()),downloader=download))
    row=next(iter(repo.rows.values()))
    assert result["state"]=="READY_FOR_ANALYSIS" and row["state"]=="READY_FOR_ANALYSIS"
    assert Path(row["normalized_path"]).is_file() and calls

def test_unsupported_document_oversized_corrupt_and_spoofed_are_bounded(tmp_path):
    cases=[
      (attachment(media_kind="IMAGE_DOCUMENT",mime_type="application/pdf"),b"", "UNSUPPORTED"),
      (attachment(reported_size_bytes=999),b"", "OVERSIZED"),
      (attachment(),b"x"*101, "OVERSIZED"),
      (attachment(),b"broken", "DECODE_FAILED"),
      (attachment(media_kind="IMAGE_DOCUMENT",mime_type="image/jpeg",original_filename="fake.jpg"),b"not image", "DECODE_FAILED"),
      (attachment(media_kind="IMAGE_DOCUMENT",mime_type="image/jpeg",original_filename="animated.gif"),image_bytes("GIF"), "UNSUPPORTED"),
    ]
    for item,data,expected in cases:
        repo=Repository();service=TelegramInboundMediaService(repository=repo,storage_root=tmp_path,maximum_bytes=100)
        async def download(*_args,**_kwargs): return data
        asyncio.run(service.process(creator_profile_id=1,fanvue_account_id=2,payload=payload(item),downloader=download))
        assert repo.rows[item.attachment_id]["state"]==expected

def test_duplicate_and_album_items_are_idempotent_with_partial_failure(tmp_path):
    repo=Repository();service=TelegramInboundMediaService(repository=repo,storage_root=tmp_path)
    group="44";first=attachment(3,grouped_id=group);second=attachment(4,grouped_id=group)
    calls=[]
    async def download(item,**_): calls.append(item.telegram_message_id);return image_bytes() if item.telegram_message_id==3 else b"bad"
    turn=payload(first,second,text="album caption")
    asyncio.run(service.process(creator_profile_id=1,fanvue_account_id=2,payload=turn,downloader=download))
    asyncio.run(service.process(creator_profile_id=1,fanvue_account_id=2,payload=turn,downloader=download))
    assert calls==[3,4]
    assert [repo.rows[x.attachment_id]["state"] for x in (first,second)]==["READY_FOR_ANALYSIS","DECODE_FAILED"]

def test_exif_orientation_and_pixel_limit_are_enforced(tmp_path):
    first_repo=Repository();first=attachment()
    async def rotated(*_args,**_kwargs): return rotated_jpeg()
    asyncio.run(TelegramInboundMediaService(repository=first_repo,storage_root=tmp_path).process(creator_profile_id=1,fanvue_account_id=2,payload=payload(first),downloader=rotated))
    with Image.open(first_repo.rows[first.attachment_id]["normalized_path"]) as result: assert result.size==(10,20)
    second_repo=Repository();second=attachment()
    async def large(*_args,**_kwargs): return image_bytes(size=(20,20))
    asyncio.run(TelegramInboundMediaService(repository=second_repo,storage_root=tmp_path,maximum_pixels=100).process(creator_profile_id=1,fanvue_account_id=2,payload=payload(second),downloader=large))
    assert second_repo.rows[second.attachment_id]["state"]=="DECODE_FAILED"

def test_normalized_jpeg_discards_original_exif_device_metadata(tmp_path):
    repo=Repository();item=attachment()
    async def with_metadata(*_args,**_kwargs): return gps_jpeg()
    asyncio.run(TelegramInboundMediaService(repository=repo,storage_root=tmp_path).process(
        creator_profile_id=1,fanvue_account_id=2,payload=payload(item),downloader=with_metadata))
    with Image.open(repo.rows[item.attachment_id]["normalized_path"]) as normalized:
        assert dict(normalized.getexif())=={}

def test_restart_from_validated_reuses_artifact_without_redownload(tmp_path):
    repo=Repository();item=attachment();path=tmp_path/"ready.jpg";path.write_bytes(image_bytes())
    repo.receive(creator_profile_id=1,fanvue_account_id=2,payload=payload(item))
    repo.rows[item.attachment_id].update(state="VALIDATED",normalized_path=str(path))
    async def forbidden(*_args,**_kwargs): raise AssertionError("validated restart must not redownload")
    asyncio.run(TelegramInboundMediaService(repository=repo,storage_root=tmp_path).process(creator_profile_id=1,fanvue_account_id=2,payload=payload(item),downloader=forbidden))
    assert repo.rows[item.attachment_id]["state"]=="READY_FOR_ANALYSIS"

def test_cleanup_deletes_only_expired_artifacts_inside_private_root(tmp_path):
    inside=tmp_path/"inside.jpg";inside.write_bytes(b"x")
    outside=tmp_path.parent/"outside-customer-media.jpg";outside.write_bytes(b"x")
    class CleanupRepository(Repository):
        def expired_artifacts(self): return [{"attachment_id":"a","normalized_path":str(inside)},{"attachment_id":"b","normalized_path":str(outside)}]
        def clear_artifact(self,key): self.rows.setdefault(key,{})["cleared"]=True
    repo=CleanupRepository();removed=TelegramInboundMediaService(repository=repo,storage_root=tmp_path).cleanup_expired()
    assert removed==1 and not inside.exists() and outside.exists()
    outside.unlink()
