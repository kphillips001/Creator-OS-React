from pathlib import Path
import json

from app.services.content_folder_scanner_service import scan_folder_for_new_content


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_FOLDER = PROJECT_ROOT / "data" / "classification_samples" / "free"


def run_test():
    print("\n========================================")
    print("13I SCAN FOLDER FOR NEW CONTENT TEST")
    print("========================================\n")

    result = scan_folder_for_new_content(
        folder_path=TEST_FOLDER,
        is_test=True,
    )

    print(json.dumps(result, indent=2))

    print("\n========================================")
    print("[DONE] Folder scan test complete")
    print("========================================\n")


if __name__ == "__main__":
    run_test()