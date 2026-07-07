from app.repositories.content_repository import get_content_ready_for_fanvue_upload
from app.services.fanvue_media_upload_service import FanvueMediaUploadService
from app.repositories.content_repository import update_content_fanvue_upload_result

def upload_single_file(service, file_path, label):
    print(f"\n=== UPLOADING {label.upper()} ===")
    print(file_path)

    session_result = service.create_upload_session(file_path)

    if not session_result.get("success"):
        print("\nUPLOAD SESSION RESULT:")
        print(session_result)
        return None

    upload_id = session_result["response"].get("uploadId")
    media_uuid = session_result["response"].get("mediaUuid")

    print("\nUpload ID:")
    print(upload_id)

    print("\nMedia UUID:")
    print(media_uuid)

    part_result = service.get_upload_part_url(upload_id, part_number=1)

    if not part_result.get("success"):
        print("\nPART URL RESULT:")
        print(part_result)
        return None

    upload_url = part_result.get("upload_url")

    if not upload_url:
        print("\nMissing upload_url from Fanvue response.")
        print(part_result)
        return None

    upload_result = service.upload_file_part(file_path, upload_url)

    print("\nFILE UPLOAD RESULT:")
    print(upload_result)

    if not upload_result.get("success"):
        return None

    etag = upload_result.get("etag")

    complete_result = service.complete_upload(
        upload_id=upload_id,
        etag=etag,
        part_number=1,
    )

    print("\nCOMPLETE UPLOAD RESULT:")
    print(complete_result)

    return media_uuid


def run_test():
    print("\n=== 14M STEP 2: FANVUE DUAL FILE UPLOAD TEST ===\n")

    queue = get_content_ready_for_fanvue_upload(limit=1)

    if not queue:
        print("No content ready for Fanvue upload.")
        return

    item = queue[0]

    preview_path = item.get("blurred_preview_path")
    full_path = item.get("file_path")

    print("\nPreview path:")
    print(preview_path)

    print("\nFull path:")
    print(full_path)

    if not preview_path:
        print("Missing blurred_preview_path.")
        return

    if not full_path:
        print("Missing file_path.")
        return

    service = FanvueMediaUploadService()

    # --- Upload Preview ---
    preview_uuid = upload_single_file(service, preview_path, "preview")

    # --- Upload Full ---
    full_uuid = upload_single_file(service, full_path, "full")

    print("\n=== FINAL RESULT ===")
    print(f"Preview UUID: {preview_uuid}")
    print(f"Full UUID: {full_uuid}")

    if preview_uuid and full_uuid:
        print("\nSaving upload results to DB...")

        update_content_fanvue_upload_result(
            content_id=item.get("id"),
            preview_uuid=preview_uuid,
            full_uuid=full_uuid,
            upload_status="processing",
            upload_error=None,
        )

        print("✅ DB updated successfully.")
    else:
        print("❌ Missing UUIDs — skipping DB save.")


if __name__ == "__main__":
    run_test()