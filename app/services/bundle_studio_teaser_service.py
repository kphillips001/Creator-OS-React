"""Bundle Studio adapter over the canonical selective-blur Bundle teaser implementation."""
from app.database import get_db_connection
from app.repositories.bundle_studio_teaser_repository import BundleStudioTeaserRepository
from app.services.photoshoot_bundle_teaser_service import PhotoshootBundleTeaserService


class _BundleProtectionAdapter:
    def has_protected_commercial_evidence(self, bundle_id, creator_profile_id):
        with get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT EXISTS(SELECT 1 FROM public.commercial_offerings o
              JOIN public.commercial_publications p ON p.commercial_offering_id=o.offering_id
              WHERE o.source_bundle_studio_bundle_id=%s AND o.creator_profile_id=%s
              AND p.status='LIVE') value""", (bundle_id, creator_profile_id))
            return bool(cursor.fetchone()["value"])


class BundleStudioTeaserService(PhotoshootBundleTeaserService):
    """Reuses the canonical renderer, mask validation, lineage, and Asset creation."""
    def __init__(self, **values):
        super().__init__(photoshoots=_BundleProtectionAdapter(),
                         repository=values.pop("repository", None) or BundleStudioTeaserRepository(), **values)

    def inspect(self, bundle_id, *, creator_profile_id: int):
        result = super().inspect(bundle_id, creator_profile_id=creator_profile_id)
        if result.get("maskUrl"):
            result["maskUrl"] = "/api/v1/bundle-studio/workspace/teaser/mask"
        return result

    def _context(self, bundle_id, creator_profile_id):
        with get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.bundle_studio_bundles WHERE bundle_id=%s AND creator_profile_id=%s", (bundle_id, creator_profile_id))
            bundle = cursor.fetchone()
            if bundle is None: raise KeyError("Bundle Studio workspace not found.")
            cursor.execute("SELECT image_id,position AS shot_order FROM public.bundle_studio_members WHERE bundle_id=%s ORDER BY position", (bundle_id,))
            source_members = tuple(cursor.fetchall())
        if not bundle.get("commercial_offering_id"): raise ValueError("Prepare the paid Bundle before creating its teaser.")
        members = []
        for item in source_members:
            asset = self.assets.get_by_generation_image_id(str(item["image_id"]))
            if asset is None: raise ValueError("Every Bundle member must be registered before teaser preparation.")
            members.append({"asset_id": int(asset.id), "shot_order": int(item["shot_order"])})
        row = {**dict(bundle), "deliverable_id": bundle["bundle_id"], "selling_mode": "BUNDLE"}
        return row, tuple(members)
