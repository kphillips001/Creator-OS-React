from app.repositories.content_repository import (
    get_approved_content,
    get_content_by_classification,
    get_content_ready_for_fanvue_upload
)

def run_test():
    print("\n=== 14K STEP 1: APPROVED CONTENT FETCH TEST ===\n")

    results = get_approved_content(limit=10)

    print("\nReturned rows:", len(results))

    for item in results:
        print(
            f"id={item.get('id')} | "
            f"classification={item.get('classification')} | "
            f"ready={item.get('ready_for_rotation')} | "
            f"preview={item.get('blurred_preview_path')}"
        )

    print("\n=== 14K STEP 2: CLASSIFICATION TEST ===\n")

    for classification in ["TEASE", "VIP", "PREMIUM"]:
        print(f"\n--- Testing {classification} ---")

        results = get_content_by_classification(classification, limit=5)

        print(f"Returned: {len(results)}")
    
        print("\n=== 14K STEP 5: FANVUE UPLOAD QUEUE TEST ===\n")

    upload_queue = get_content_ready_for_fanvue_upload(limit=10)

    print("Upload queue count:", len(upload_queue))

    for item in upload_queue:
        print(
            f"id={item.get('id')} | "
            f"classification={item.get('classification')} | "
            f"status={item.get('status')} | "
            f"ready={item.get('ready_for_rotation')} | "
            f"upload_status={item.get('upload_status')} | "
            f"preview={item.get('blurred_preview_path')}"
        )


if __name__ == "__main__":
    run_test()