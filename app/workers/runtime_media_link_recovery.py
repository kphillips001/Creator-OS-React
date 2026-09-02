"""One-shot worker entry point for durable runtime Media Link recovery."""
from app.services.runtime_media_link_recovery_service import RuntimeMediaLinkRecoveryService


def run_once(*, limit=25):
    return RuntimeMediaLinkRecoveryService().run_once(limit=limit)


if __name__ == "__main__":
    run_once()
