"""Prepare every paid Photoshoot Session strategy step for Fanvue delivery."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import UUID

from app.models.commercial_offering import CommercialOfferingStatus
from app.models.commercial_publication import (
    CommercialPublicationProvider, CommercialPublicationStatus,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.repositories.commercial_publication_upload_repository import CommercialPublicationUploadRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.repositories.photoshoot_session_sales_strategy_repository import PhotoshootSessionSalesStrategyRepository
from app.services.commercial_offering_service import CommercialOfferingService
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.fanvue_media_link_publication_executor import FanvueMediaLinkPublicationExecutor


class PhotoshootSalePreparationService:
    WORKFLOW = "photoshoot_session_sale_preparation"

    def __init__(self, *, photoshoots=None, strategies=None, assets=None,
                 offerings=None, publications=None, uploads=None,
                 offering_service=None, publication_service=None, executor=None):
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.strategies = strategies or PhotoshootSessionSalesStrategyRepository()
        self.assets = assets or AssetRepository()
        self.offerings = offerings or CommercialOfferingRepository()
        self.publications = publications or CommercialPublicationRepository()
        self.uploads = uploads or CommercialPublicationUploadRepository()
        self.offering_service = offering_service or CommercialOfferingService(
            repository=self.offerings, asset_repository=self.assets,
            publication_repository=self.publications, photoshoot_repository=self.photoshoots,
        )
        self.publication_service = publication_service or CommercialPublicationService(
            repository=self.publications, offering_repository=self.offerings,
        )
        self.executor = executor or FanvueMediaLinkPublicationExecutor(
            publications=self.publications, offerings=self.offerings, assets=self.assets,
            uploads=self.uploads, publication_service=self.publication_service,
        )

    def inspect(self, deliverable_id, *, creator_profile_id: int):
        row = self._deliverable(deliverable_id, creator_profile_id)
        if str(row.get("selling_mode") or "SESSION") == "BUNDLE":
            return {
                "deliverableId": str(row["deliverable_id"]),
                "photoshootSessionId": str(row["photoshoot_session_id"]),
                "sellingMode": "BUNDLE",
                "strategyVersion": "",
                "status": "NOT_CONFIGURED",
                "statusLabel": "Bundle preparation is not configured yet",
                "paidStepCount": 0,
                "readyPaidStepCount": 0,
                "teaserReady": False,
                "steps": [],
            }
        strategy = self._strategy(row)
        if strategy is None:
            return {
                "deliverableId": str(row["deliverable_id"]),
                "photoshootSessionId": str(row["photoshoot_session_id"]),
                "sellingMode": "SESSION", "strategyVersion": "",
                "strategyExists": False, "strategyStatus": "MISSING",
                "status": "STRATEGY_REQUIRED", "statusLabel": "Not Prepared",
                "paidStepCount": 0, "readyPaidStepCount": 0,
                "teaserReady": False, "steps": [],
            }
        steps = [self._step_projection(row, strategy, shot) for shot in self._ordered(strategy)]
        paid = [step for step in steps if step["access"] == "PAID"]
        ready_paid = sum(step["ready"] for step in paid)
        prepared = any(step.get("offeringId") for step in paid)
        failed = any(step.get("publicationStatus") == "FAILED" or step.get("error") for step in paid)
        preparing = any(step.get("publicationStatus") in {"READY_TO_PUBLISH", "PUBLISHING"} for step in paid)
        teaser_ready = all(step["ready"] for step in steps if step["access"] == "FREE")
        all_ready = bool(steps) and ready_paid == len(paid) and teaser_ready
        needs_attention = failed or (prepared and not all_ready and not preparing)
        status = "READY" if all_ready else "NEEDS_ATTENTION" if needs_attention else "PREPARING" if preparing else "NOT_PREPARED"
        return {
            "deliverableId": str(row["deliverable_id"]),
            "photoshootSessionId": str(row["photoshoot_session_id"]),
            "sellingMode": "SESSION",
            "strategyVersion": strategy.strategy_version,
            "status": status,
            "statusLabel": {
                "READY": "Ready for Session Selling", "NEEDS_ATTENTION": "Needs Attention",
                "PREPARING": "Preparing", "NOT_PREPARED": "Not Prepared",
            }[status],
            "paidStepCount": len(paid), "readyPaidStepCount": ready_paid,
            "teaserReady": teaser_ready, "steps": steps,
        }

    def stage(self, deliverable_id, *, creator_profile_id: int, fanvue_account_id: int,
              strategy_version: str, reviewed_steps: list[dict], retry_failed: bool = False):
        row, strategy = self._context(deliverable_id, creator_profile_id)
        prices = self._validate_review(
            row, strategy, strategy_version=strategy_version,
            reviewed_steps=reviewed_steps, creator_profile_id=creator_profile_id,
        )
        staged = []
        for shot in self._ordered(strategy):
            if str(shot.access_recommendation).upper() != "PAID":
                continue
            price = prices[shot.asset_id]
            offering = self._offering(row, strategy, shot, creator_profile_id, price)
            publication = self.publications.get_by_offering_provider(
                offering.offering_id, CommercialPublicationProvider.FANVUE,
            )
            metadata = {
                **dict(publication.publication_metadata if publication else {}),
                "source_workflow": self.WORKFLOW,
                "fanvue_account_id": int(fanvue_account_id),
                "photoshoot_session_id": str(row["photoshoot_session_id"]),
                "photoshoot_deliverable_id": str(row["deliverable_id"]),
                "strategy_version": strategy.strategy_version,
                "strategy_position": int(shot.sales_position),
                "shot_order": int(shot.shot_order), "session_role": shot.sales_role,
                "asset_id": int(shot.asset_id), "price_minor": price, "currency": "USD",
            }
            if publication is None:
                publication = self.publication_service.create_publication(
                    creator_profile_id=creator_profile_id,
                    commercial_offering_id=offering.offering_id,
                    provider="FANVUE", publication_metadata=metadata,
                )
            elif publication.status == CommercialPublicationStatus.LIVE:
                self.offerings.update_status(
                    offering.offering_id, creator_profile_id=creator_profile_id,
                    status=CommercialOfferingStatus.READY,
                )
                staged.append(publication.publication_id)
                continue
            else:
                self.publications.update_metadata(
                    publication.publication_id, creator_profile_id=creator_profile_id,
                    metadata=metadata,
                )
                publication = self.publication_service.get_publication(
                    publication.publication_id, creator_profile_id=creator_profile_id,
                )
            if publication.status == CommercialPublicationStatus.FAILED:
                publication = self.publication_service.update_status(
                    publication.publication_id, creator_profile_id=creator_profile_id,
                    status="PUBLISHING",
                )
            elif publication.status == CommercialPublicationStatus.READY_TO_PUBLISH:
                publication = self.publication_service.update_status(
                    publication.publication_id, creator_profile_id=creator_profile_id,
                    status="PUBLISHING",
                )
            elif publication.status != CommercialPublicationStatus.PUBLISHING:
                raise ValueError(f"Publication for Shot {shot.shot_order} cannot be prepared.")
            staged.append(publication.publication_id)
        return tuple(staged)

    def _validate_review(self, row, strategy, *, strategy_version: str,
                         reviewed_steps: list[dict], creator_profile_id: int):
        if strategy_version != strategy.strategy_version:
            raise ValueError("Session Sales Strategy changed. Reopen pricing review.")
        expected = self._ordered(strategy)
        expected_ids = [int(shot.asset_id) for shot in expected]
        if len(expected_ids) != len(set(expected_ids)):
            raise ValueError("Session Sales Strategy contains duplicate Assets.")
        submitted_ids = [int(item.get("assetId", 0)) for item in reviewed_steps]
        if len(submitted_ids) != len(set(submitted_ids)):
            raise ValueError("Pricing review contains duplicate Assets.")
        if len(reviewed_steps) != len(expected) or set(submitted_ids) != set(expected_ids):
            raise ValueError("Pricing review must contain every strategy step exactly once.")
        if submitted_ids != expected_ids:
            raise ValueError("Pricing review steps must remain in canonical sales order.")

        submitted = {int(item["assetId"]): item for item in reviewed_steps}
        prices = {}
        for shot in expected:
            if self.assets.get_by_id(shot.asset_id) is None:
                raise ValueError(f"Canonical Asset {shot.asset_id} for Shot {shot.shot_order} was not found.")
            item = submitted[int(shot.asset_id)]
            access = str(shot.access_recommendation).upper()
            if access not in {"FREE", "PAID"}:
                raise ValueError(f"Shot {shot.shot_order} has an unsupported access recommendation.")
            if (
                int(item.get("shotOrder", 0)) != int(shot.shot_order)
                or int(item.get("salesPosition", 0)) != int(shot.sales_position)
                or str(item.get("role") or "") != str(shot.sales_role)
                or str(item.get("access") or "").upper() != access
            ):
                raise ValueError(f"Pricing review does not match canonical Shot {shot.shot_order}.")
            if str(item.get("currency") or "USD").upper() != "USD":
                raise ValueError("Session Selling prices must use USD.")
            price = item.get("priceMinor")
            if access == "FREE":
                if price is not None:
                    raise ValueError(f"FREE_TEASER Shot {shot.shot_order} cannot have a price.")
                continue
            if isinstance(price, bool) or not isinstance(price, int) or not 300 <= price <= 50000:
                raise ValueError(f"Shot {shot.shot_order} price must be between 300 and 50,000 minor units.")
            prices[int(shot.asset_id)] = price
            self._validate_existing_price(
                row, shot, creator_profile_id=creator_profile_id, price=price,
            )
        return prices

    def _validate_existing_price(self, row, shot, *, creator_profile_id: int, price: int):
        offering = self.offerings.get_by_idempotency_key(
            creator_profile_id=creator_profile_id,
            idempotency_key=self._idempotency_key(row, shot),
        )
        if offering is None:
            return
        if len(offering.assets) != 1 or offering.assets[0].asset_id != shot.asset_id:
            raise ValueError(f"Session Offering mapping is ambiguous for Shot {shot.shot_order}.")
        publication = self.publications.get_by_offering_provider(
            offering.offering_id, CommercialPublicationProvider.FANVUE,
        )
        if publication and publication.status == CommercialPublicationStatus.LIVE:
            link_url = str((publication.publication_metadata.get("media_link") or {}).get("url") or "").strip()
            if publication.provider_resource_status.value != "PRESENT" or not link_url:
                raise ValueError(f"Shot {shot.shot_order} has a LIVE publication requiring reconciliation.")
            published_price = int(publication.publication_metadata.get("price_minor") or offering.price_minor or 0)
            if price != published_price or offering.price_minor != published_price:
                raise ValueError(
                    f"Shot {shot.shot_order} is already LIVE at USD {published_price / 100:.2f}. "
                    "Fanvue does not currently support editing a live Media Link price; keep the existing price or cancel."
                )
        elif publication and publication.status == CommercialPublicationStatus.PUBLISHING and offering.price_minor != price:
            raise ValueError(f"Shot {shot.shot_order} is already publishing and cannot be repriced.")

    def execute_staged(self, publication_ids, *, creator_profile_id: int, fanvue_account_id: int):
        results = []
        for publication_id in publication_ids:
            publication = self.publication_service.get_publication(
                publication_id, creator_profile_id=creator_profile_id,
            )
            if publication is None or publication.status == CommercialPublicationStatus.LIVE:
                continue
            try:
                results.append(self.executor.execute(
                    publication_id, creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id,
                ))
            except Exception as error:
                results.append({"publicationId": str(publication_id), "error": type(error).__name__})
        return tuple(results)

    def _offering(self, row, strategy, shot, creator_profile_id, price):
        key = self._idempotency_key(row, shot)
        existing = self.offerings.get_by_idempotency_key(
            creator_profile_id=creator_profile_id, idempotency_key=key,
        )
        if existing:
            if len(existing.assets) != 1 or existing.assets[0].asset_id != shot.asset_id:
                raise ValueError(f"Session Offering mapping is ambiguous for Shot {shot.shot_order}.")
            if existing.price_minor != price and existing.status != CommercialOfferingStatus.READY:
                existing = self.offerings.update_pricing(
                    existing.offering_id, creator_profile_id=creator_profile_id,
                    price_minor=price, currency="USD",
                )
            if existing.price_minor != price:
                raise ValueError(f"Published price for Shot {shot.shot_order} cannot be changed.")
            return existing
        return self.offering_service.create(
            creator_profile_id=creator_profile_id, offering_type="SINGLE_IMAGE",
            title=f"Shot {shot.shot_order} — {shot.sales_role.replace('_', ' ').title()}",
            description=shot.customer_journey_purpose, hero_asset_id=shot.asset_id,
            primary_sales_channel="AI_CHAT", asset_ids=(shot.asset_id,),
            price_minor=price, currency="USD", initial_status=CommercialOfferingStatus.DRAFT,
            source_photoshoot_deliverable_id=UUID(str(row["deliverable_id"])),
            idempotency_key=key,
        )

    def _step_projection(self, row, strategy, shot):
        asset = self.assets.get_by_id(shot.asset_id)
        access = str(shot.access_recommendation).upper()
        base = {"assetId": shot.asset_id, "shotOrder": shot.shot_order,
                "position": shot.sales_position, "role": shot.sales_role, "access": access,
                "imageUrl": f"/api/v1/assets/{shot.asset_id}/thumbnail"}
        if access == "FREE":
            path = getattr(asset, "local_vault_path", None) or getattr(asset, "file_path", None)
            return {**base, "ready": bool(asset and path and Path(path).is_file()),
                    "deliveryMethod": "Direct Telegram delivery"}
        key = self._idempotency_key(row, shot)
        offering = self.offerings.get_by_idempotency_key(
            creator_profile_id=strategy.creator_profile_id, idempotency_key=key,
        )
        publication = (self.publications.get_by_offering_provider(
            offering.offering_id, CommercialPublicationProvider.FANVUE,
        ) if offering else None)
        metadata = dict(publication.publication_metadata if publication else {})
        link = dict(metadata.get("media_link") or {})
        uploads = self.uploads.list_for_publication(publication.publication_id) if publication else ()
        upload = next((item for item in uploads if item.asset_id == shot.asset_id), None)
        url = str(link.get("url") or "").strip() or None
        ready = bool(
            offering and offering.status == CommercialOfferingStatus.READY
            and publication and publication.status == CommercialPublicationStatus.LIVE
            and publication.provider_resource_status.value == "PRESENT" and url
            and len(offering.assets) == 1 and offering.assets[0].asset_id == shot.asset_id
        )
        live_present = bool(
            publication and publication.status == CommercialPublicationStatus.LIVE
            and publication.provider_resource_status.value == "PRESENT" and url
        )
        published_price = int(metadata.get("price_minor") or offering.price_minor or 0) if offering else None
        price_conflict = None
        if live_present and offering and offering.price_minor != published_price:
            price_conflict = "Stored Offering price differs from the published Fanvue Media Link price."
        return {**base, "ready": ready,
                "offeringId": str(offering.offering_id) if offering else None,
                "offeringStatus": offering.status.value if offering else None,
                "publicationId": str(publication.publication_id) if publication else None,
                "publicationStatus": publication.status.value if publication else None,
                "providerResourceStatus": publication.provider_resource_status.value if publication else None,
                "mediaUuid": upload.provider_media_uuid if upload else None,
                "mediaLinkUuid": publication.external_product_id if publication else None,
                "deliveryUrl": url,
                "priceMinor": published_price if live_present else offering.price_minor if offering else None,
                "currency": offering.currency if offering else "USD",
                "priceLocked": live_present, "priceConflict": price_conflict,
                "publishedAt": publication.published_at.isoformat() if publication and publication.published_at else None,
                "updatedAt": publication.updated_at.isoformat() if publication else None,
                "error": publication.last_error if publication else None}

    def _context(self, deliverable_id, creator_profile_id):
        row = self._deliverable(deliverable_id, creator_profile_id)
        if str(row.get("selling_mode") or "SESSION") != "SESSION":
            raise ValueError(
                "Session sale preparation is unavailable while this Photoshoot uses BUNDLE selling mode."
            )
        strategy = self._strategy(row)
        if strategy is None:
            raise ValueError("Generate a Session Sales Strategy before preparing this Photoshoot.")
        return row, strategy

    def _deliverable(self, deliverable_id, creator_profile_id):
        row = self.photoshoots.get(str(deliverable_id))
        if row is None or int(row["creator_profile_id"]) != int(creator_profile_id):
            raise KeyError("Photoshoot not found.")
        if row["registration_state"] not in {"IN_ASSET_LIBRARY", "REGISTERED"}:
            raise ValueError("Photoshoot must be in the Asset Library.")
        return row

    def _strategy(self, row):
        return self.strategies.latest(str(row["photoshoot_session_id"]))

    @staticmethod
    def _ordered(strategy):
        return tuple(sorted(strategy.shots, key=lambda shot: (shot.sales_position, shot.asset_id)))

    def _idempotency_key(self, row, shot):
        return sha256(
            f"{self.WORKFLOW}:{row['photoshoot_session_id']}:{shot.asset_id}".encode()
        ).hexdigest()
