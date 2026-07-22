from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService

if __name__ == "__main__":
    for item in PhotoshootCommerceDeliverableService().reconcile_completed():
        print(item["photoshoot_session_id"], item["deliverable_id"], item["shot_count"], item["intelligence_status"])
