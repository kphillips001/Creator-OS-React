"""Unified Asset Library projection for canonical BUNDLE offerings."""
from app.database import get_db_connection
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultService
from app.services.bundle_studio_sale_preparation_service import BundleStudioSalePreparationService
from app.services.photoshoot_bundle_sale_preparation_service import PhotoshootBundleSalePreparationService


class BundleLibraryService:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory = connection_factory

    def list(self, *, creator_profile_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT o.*,b.name bundle_studio_name,d.display_name photoshoot_name,
              p.publication_id fanvue_publication_id,p.status fanvue_status,p.publication_metadata fanvue_metadata
              FROM public.commercial_offerings o
              LEFT JOIN public.bundle_studio_bundles b ON b.bundle_id=o.source_bundle_studio_bundle_id
              LEFT JOIN public.photoshoot_commerce_deliverables d ON d.deliverable_id=o.source_photoshoot_deliverable_id
              LEFT JOIN public.commercial_publications p ON p.commercial_offering_id=o.offering_id AND p.provider='FANVUE'
              WHERE o.creator_profile_id=%s AND o.offering_type='BUNDLE' AND o.status<>'ARCHIVED'
              ORDER BY o.updated_at DESC""", (creator_profile_id,))
            rows = tuple(cursor.fetchall())
            result = []
            for row in rows:
                cursor.execute("""SELECT m.asset_id,m.position,a.file_name FROM public.commercial_offering_assets m
                  JOIN public.content_items a ON a.id=m.asset_id WHERE m.offering_id=%s ORDER BY m.position""", (row["offering_id"],))
                members = tuple(cursor.fetchall())
                metadata = dict(row.get("fanvue_metadata") or {}); link = dict(metadata.get("media_link") or {})
                wall = str(row["primary_sales_channel"]) == "TELEGRAM_WALL"
                preparation = None
                if row.get("source_bundle_studio_bundle_id"):
                    preparation = BundleStudioSalePreparationService().inspect(row["source_bundle_studio_bundle_id"], creator_profile_id=creator_profile_id)
                elif row.get("source_photoshoot_deliverable_id"):
                    preparation = PhotoshootBundleSalePreparationService().inspect(
                        row["source_photoshoot_deliverable_id"], creator_profile_id=creator_profile_id)
                publication = (
                    preparation.get("contentVaultPublication") if wall and preparation
                    else CommerceTelegramVaultService().status(
                        row["offering_id"], creator_profile_id=creator_profile_id)
                    if wall and str(row["status"]) == "READY" else None
                )
                result.append({
                    "offeringId":str(row["offering_id"]), "title":row.get("bundle_studio_name") or row.get("photoshoot_name") or row["title"],
                    "source":"BUNDLE_STUDIO" if row.get("source_bundle_studio_bundle_id") else "PHOTOSHOOT",
                    "sourceId":str(row.get("source_bundle_studio_bundle_id") or row.get("source_photoshoot_deliverable_id")),
                    "status":str(row["status"]), "destination":"WALL" if wall else "CHAT",
                    "priceMinor":row.get("price_minor"), "currency":row.get("currency") or "USD",
                    "memberCount":len(members), "members":[{"assetId":int(item["asset_id"]),"position":int(item["position"]),"imageUrl":f'/api/v1/assets/{int(item["asset_id"])}/thumbnail'} for item in members],
                    "heroImageUrl":f'/api/v1/assets/{int(row["hero_asset_id"])}/thumbnail',
                    "fanvueStatus":row.get("fanvue_status"), "deliveryUrl":link.get("url"),
                    "readinessStatus":preparation.get("status") if preparation else str(row["status"]),
                    "contentVaultPublication":publication,
                    "preparation":preparation,
                })
        return result
