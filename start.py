import subprocess
import sys
import time

from app.services.local_vault_service import LocalVaultService


def start_process(command):
    return subprocess.Popen(
        command,
    )


if __name__ == "__main__":
    vault_paths = LocalVaultService().initialize()
    print(f"CMS workspace ready: {vault_paths['cms_root']}")

    print("🚀 Starting Fanvue Callback Server (port 8000)...")

    callback_server = start_process(
        [sys.executable, "-m", "uvicorn", "app.fanvue_callback_server:app", "--port", "8000"]
    )

    # Give it a second to boot
    time.sleep(2)

    print("🚀 Starting Streamlit Dashboard (port 8501)...")

    dashboard = start_process(
        [sys.executable, "-m", "streamlit", "run", "app/dashboard/main.py"]
    )

    try:
        dashboard.wait()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down servers...")

        callback_server.terminate()
        dashboard.terminate()

        callback_server.wait(timeout=5)
        dashboard.wait(timeout=5)

        sys.exit(0)
