import random
from pathlib import Path
from app.services.blur_service import generate_blurred_preview


def get_random_image(upload_dir="data/uploads"):
    files = list(Path(upload_dir).glob("*"))

    if not files:
        return None

    return str(random.choice(files))


def run_test():
    test_image = get_random_image()

    if not test_image:
        print("❌ No images found in data/uploads")
        return

    print(f"🧪 Testing with: {test_image}")

    try:
        blurred_path = generate_blurred_preview(test_image)

        print("✅ Blur successful!")
        print(f"Blurred file saved at: {blurred_path}")

    except Exception as e:
        print("❌ Blur failed:")
        print(e)


if __name__ == "__main__":
    run_test()