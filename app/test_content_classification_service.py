from pathlib import Path
import json

from app.services.content_classification_service import classify_content_image
from app.repositories.content_repository import get_content_by_classification


PROJECT_ROOT = Path(__file__).resolve().parent.parent

TEST_IMAGE = (
    PROJECT_ROOT
    / "data"
    / "classification_samples"
    / "free"
    / "tease_test_2.png"
)


def run_test():
    print("\n========================================")
    print("CONTENT CLASSIFICATION SERVICE TEST")
    print("========================================\n")

    # ----------------------------------------
    # STEP 1 — CLASSIFY IMAGE
    # ----------------------------------------
    print("[STEP 1] Running classification...\n")

    result = classify_content_image(
        image_path=TEST_IMAGE,
        save_to_db=True,
        is_test=True,
    )

    print(json.dumps(result, indent=2))

    final_class = result.get("final_classification")

    print("\n[FINAL CLASSIFICATION]:", final_class)

    # ----------------------------------------
    # STEP 2 — VERIFY DB SAVE
    # ----------------------------------------
    print("\n[STEP 2] Verifying DB save...\n")

    db_result = result.get("db_save_result", {})

    if db_result.get("success"):
        print("✅ Saved to DB successfully")
    else:
        print("❌ Failed to save to DB:", db_result)

    # ----------------------------------------
    # STEP 3 — VERIFY RETRIEVAL (CRITICAL)
    # ----------------------------------------
    print("\n[STEP 3] Fetching TEASE content from DB...\n")

    tease_content = get_content_by_classification("TEASE")

    if tease_content:
        print(f"✅ TEASE content FOUND ({len(tease_content)} items)\n")

        print(tease_content)
    else:
        print("❌ NO TEASE CONTENT FOUND (THIS IS WHY OUTREACH IS TEXT ONLY)")

    print("\n========================================")
    print("[DONE] Test complete")
    print("========================================\n")


if __name__ == "__main__":
    run_test()