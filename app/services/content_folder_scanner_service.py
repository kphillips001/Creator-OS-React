from pathlib import Path

from app.repositories.content_repository import has_content_file_been_scanned
from app.services.ai_import_workflow_service import AIImportWorkflowService


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_AI_IMPORT_WORKFLOW = AIImportWorkflowService()


def scan_folder_for_new_content(folder_path: str | Path, is_test: bool = True) -> dict:
    folder_path = Path(folder_path)

    if not folder_path.exists():
        return {
            "success": False,
            "error": f"Folder not found: {folder_path}",
        }

    scanned = []
    skipped = []
    errors = []

    for image_path in folder_path.iterdir():
        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        if has_content_file_been_scanned(str(image_path)):
            skipped.append(str(image_path))
            continue

        result = _AI_IMPORT_WORKFLOW.import_asset(
            media_path=image_path,
            upload_intent="ppv_image",
            creator_profile_id=None,
            create_product_draft=True,
            provider_upload_enabled=True,
            is_test=is_test,
        ).to_legacy_result()

        if result.get("success"):
            scanned.append({
                "image_path": str(image_path),
                "final_classification": result.get("final_classification"),
                "db_saved": result.get("db_save_result", {}).get("saved"),
            })
        else:
            errors.append({
                "image_path": str(image_path),
                "error": result.get("error"),
            })

    return {
        "success": True,
        "folder": str(folder_path),
        "scanned_count": len(scanned),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "scanned": scanned,
        "skipped": skipped,
        "errors": errors,
    }
