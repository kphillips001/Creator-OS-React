from app.services.fanvue_api_service import FanvueAPIService


def run_test():
    print("\n========================================")
    print("13D TEST — LIST VAULT FOLDERS")
    print("========================================\n")

    service = FanvueAPIService()

    print("[STEP 1] Fetch vault folders\n")

    result = service.list_vault_folders()

    print("\n----------- RESULT -----------")
    print(f"success: {result.get('success')}")

    if not result.get("success"):
        print("❌ Failed to fetch folders")
        print(result)
        return

    folders = result.get("data", [])

    print(f"\nTotal folders found: {len(folders)}\n")

    print("----------- RAW FOLDER DATA -----------")

    for i, folder in enumerate(folders, start=1):
        print(f"\n[FOLDER #{i}]")
        print(folder)

    print("\n----------- PARSED FOLDERS -----------")

    for folder in folders:
        # 🔥 Flexible parsing (Fanvue inconsistency safe)
        folder_uuid = (
            folder.get("uuid")
            or folder.get("id")
            or folder.get("folderId")
        )

        folder_name = (
            folder.get("name")
            or folder.get("title")
            or folder.get("folderName")
        )

        print(f"{folder_name} → {folder_uuid}")

    print("\n========================================")
    print("13D TEST COMPLETE")
    print("========================================\n")


if __name__ == "__main__":
    run_test()