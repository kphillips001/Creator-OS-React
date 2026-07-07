"""Idempotent Phase 1C draft-product backfill."""

import json
from dataclasses import asdict, dataclass

from app.repositories.asset_repository import AssetRepository
from app.repositories.experience_repository import ExperienceRepository
from app.repositories.product_asset_repository import ProductAssetRepository
from app.repositories.product_repository import ProductRepository
from app.services.experience_service import ExperienceService


@dataclass(frozen=True)
class CommerceBackfillResult:
    content_items_seen: int
    products_created: int
    products_existing: int
    product_assets_created: int
    product_assets_existing: int


class CommerceFoundationBackfillService:
    """Migration-only utility for legacy content_items -> Product drafts."""

    def __init__(
        self,
        asset_repository: AssetRepository | None = None,
        product_repository: ProductRepository | None = None,
        product_asset_repository: ProductAssetRepository | None = None,
        experience_service: ExperienceService | None = None,
    ):
        self._assets = asset_repository or AssetRepository()
        self._products = product_repository or ProductRepository()
        # Kept only to construct the Experience compatibility boundary below.
        self._product_assets = product_asset_repository or ProductAssetRepository()
        self._experiences = experience_service or ExperienceService(
            ExperienceRepository(
                product_repository=self._products,
                product_asset_repository=self._product_assets,
            )
        )

    def run(self) -> CommerceBackfillResult:
        products_created = 0
        product_assets_created = 0
        # A.2 compatibility boundary: this is a legacy Product backfill, so it
        # intentionally consumes the broad Asset model and not Asset-owned rows.
        # Future Product migration should replace this with a Product-specific
        # source contract or retire the backfill once complete.
        assets = self._assets.list_all()

        for asset in assets:
            product, created = self._products.create_draft_for_asset(asset)
            products_created += int(created)
            _, link_created = (
                self._experiences.attach_primary_product_experience_asset(
                    product.id,
                    asset.id,
                )
            )
            product_assets_created += int(link_created)

        return CommerceBackfillResult(
            content_items_seen=len(assets),
            products_created=products_created,
            products_existing=len(assets) - products_created,
            product_assets_created=product_assets_created,
            product_assets_existing=len(assets) - product_assets_created,
        )


def main() -> None:
    result = CommerceFoundationBackfillService().run()
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
