"""Authoring-only round trip for a generated Session opener."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.database import get_db_connection
from app.models.asset_lineage import DerivationKind
from app.repositories.asset_repository import AssetRepository
from app.services.asset_registration_service import AssetRegistrationService
from app.services.generation_library_service import GenerationLibraryService


class PhotoshootSessionTeaserService:
    PURPOSE = "PHOTOSHOOT_SESSION_TEASER"

    def __init__(self, *, connection_factory=get_db_connection, assets=None, library=None,
                 registration=None):
        self.connection_factory = connection_factory
        self.assets = assets or AssetRepository()
        self.library = library or GenerationLibraryService()
        self.registration = registration or AssetRegistrationService(
            generation_library_service=self.library, analyze_on_registration=False)

    def eligibility(self, deliverable_id: str, *, creator_profile_id: int) -> dict:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._locked_context(cursor, deliverable_id, creator_profile_id, lock=False)
        eligible, reason = self._eligibility(row)
        return {"eligible": eligible, "reason": reason,
                "sourceAssetId": int(row["source_asset_id"]) if row and row.get("source_asset_id") else None,
                "hasSessionTeaser": bool(row and row.get("existing_teaser_asset_id"))}

    def create_intent(self, deliverable_id: str, *, creator_profile_id: int) -> dict:
        current = self.library.pending_edit_record(creator_profile_id=creator_profile_id)
        if current is not None:
            if dict(current.generation_metadata or {}).get("purpose") == self.PURPOSE:
                self.cancel_active(creator_profile_id=creator_profile_id)
            else:
                for record in self.library.list_records():
                    if (record.status == "edit_candidate" and
                            dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == current.image_id):
                        result = self.library.discard_edit_candidate(record.image_id)
                        if not result.success:
                            raise ValueError(result.message)
                result = self.library.return_pending_edit_to_library(current.image_id)
                if not result.success:
                    raise ValueError(result.message)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._locked_context(cursor, deliverable_id, creator_profile_id, lock=True)
            eligible, reason = self._eligibility(row)
            if not eligible:
                raise ValueError(reason)
            cursor.execute("""UPDATE public.photoshoot_session_teaser_edit_intents
                SET status='CANCELLED',completed_at=NOW()
                WHERE creator_profile_id=%s AND status='ACTIVE'""", (creator_profile_id,))
        source = self.assets.get_by_id(int(row["source_asset_id"]))
        if source is None or int(source.creator_profile_id or 0) != int(creator_profile_id):
            raise ValueError("Current Shot 1 is unavailable for editing.")
        source_path = str(source.local_vault_path or source.file_path or "")
        if not Path(source_path).is_file():
            raise ValueError("Current Shot 1 media is unavailable for editing.")
        intent_id = uuid4()
        workspace = self.library.create_asset_edit_workspace_source(
            creator_profile_id=creator_profile_id, asset_id=int(source.id), source_path=source_path,
            metadata={"purpose": self.PURPOSE, "teaser_intent_id": str(intent_id),
                      "origin_deliverable_id": str(deliverable_id),
                      "origin_photoshoot_id": str(row["photoshoot_session_id"]),
                      "source_asset_id": int(source.id), "source_shot_order": 1},
        )
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO public.photoshoot_session_teaser_edit_intents
                (intent_id,creator_profile_id,deliverable_id,photoshoot_session_id,
                 source_asset_id,workspace_image_id,metadata)
                VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (intent_id, creator_profile_id, deliverable_id, row["photoshoot_session_id"],
                 source.id, workspace.image_id, json.dumps({"replacement": bool(row.get("existing_teaser_asset_id"))})))
        return {"intentId": str(intent_id), "redirect": "/content/edit",
                "workspaceImageId": workspace.image_id}

    def use_candidate(self, intent_id: str, candidate_image_id: str, *, creator_profile_id: int) -> dict:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.photoshoot_session_teaser_edit_intents
                WHERE intent_id=%s AND creator_profile_id=%s AND status='ACTIVE' FOR UPDATE""",
                (intent_id, creator_profile_id))
            intent = cursor.fetchone()
        if intent is None:
            raise ValueError("Session teaser edit intent is no longer active.")
        candidate = self.library.get(candidate_image_id)
        metadata = dict(candidate.generation_metadata or {})
        if (candidate.creator_profile_id != creator_profile_id or candidate.status != "edit_candidate"
                or metadata.get("edit_pending_source_image_id") != intent["workspace_image_id"]):
            raise ValueError("Selected result does not belong to this Session teaser edit intent.")
        registered = self.registration.register_generated_image(
            candidate, creator_profile_id=creator_profile_id,
            classification="SINGLE_IMAGE", finalize_generation=False)
        if not registered.success or not registered.asset_id:
            raise ValueError(registered.message or "Teaser result could not be registered.")
        teaser_asset_id = int(registered.asset_id)
        try:
            result = self._insert_transaction(intent, teaser_asset_id, candidate_image_id,
                                              creator_profile_id)
        except Exception:
            # Registration precedes the membership transaction; make an orphaned result unavailable.
            with self.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE public.content_items SET is_active=FALSE,status='rejected' WHERE id=%s", (teaser_asset_id,))
            raise
        self.library.mark_registered(candidate_image_id, teaser_asset_id)
        for record in self.library.list_records():
            if (record.status == "edit_candidate" and record.image_id != candidate_image_id and
                    dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == intent["workspace_image_id"]):
                self.library.discard_edit_candidate(record.image_id)
        self.library.remove_asset_edit_workspace_source(str(intent["workspace_image_id"]))
        return result

    def cancel_active(self, *, creator_profile_id: int) -> dict:
        source = self.library.pending_edit_record(creator_profile_id=creator_profile_id)
        if source is None or dict(source.generation_metadata or {}).get("purpose") != self.PURPOSE:
            raise ValueError("No active Session teaser edit intent was found.")
        for record in self.library.list_records():
            if (record.status == "edit_candidate" and
                    dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == source.image_id):
                self.library.discard_edit_candidate(record.image_id)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.photoshoot_session_teaser_edit_intents
                SET status='CANCELLED',completed_at=NOW()
                WHERE creator_profile_id=%s AND workspace_image_id=%s AND status='ACTIVE'""",
                (creator_profile_id, source.image_id))
        self.library.remove_asset_edit_workspace_source(source.image_id)
        return {"success": True, "message": "Session teaser editing cancelled. The Photoshoot was not changed."}

    def _insert_transaction(self, intent, teaser_asset_id: int, candidate_image_id: str,
                            creator_profile_id: int) -> dict:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._locked_context(cursor, str(intent["deliverable_id"]), creator_profile_id, lock=True)
            eligible, reason = self._eligibility(row)
            if not eligible:
                raise ValueError(reason)
            if int(row["source_asset_id"]) != int(intent["source_asset_id"]):
                raise ValueError("Shot 1 changed while the teaser was being edited. Start again.")
            old_teaser = int(row["existing_teaser_asset_id"]) if row.get("existing_teaser_asset_id") else None
            session_id = str(row["photoshoot_session_id"])
            if old_teaser:
                cursor.execute("""UPDATE public.photoshoot_asset_memberships SET asset_id=%s,
                    is_hero=TRUE,updated_at=NOW() WHERE photoshoot_session_id=%s AND asset_id=%s AND shot_order=1""",
                    (teaser_asset_id, session_id, old_teaser))
            else:
                cursor.execute("""UPDATE public.photoshoot_asset_memberships SET
                    shot_order=shot_order+10000,is_hero=FALSE,updated_at=NOW()
                    WHERE photoshoot_session_id=%s AND approved=TRUE""", (session_id,))
                cursor.execute("""UPDATE public.photoshoot_asset_memberships SET
                    shot_order=shot_order-9999,updated_at=NOW()
                    WHERE photoshoot_session_id=%s AND approved=TRUE""", (session_id,))
                cursor.execute("""INSERT INTO public.photoshoot_asset_memberships
                    (photoshoot_session_id,asset_id,shot_order,approved,is_hero)
                    VALUES(%s,%s,1,TRUE,TRUE)""", (session_id, teaser_asset_id))
            cursor.execute("""SELECT asset_id FROM public.photoshoot_asset_memberships
                WHERE photoshoot_session_id=%s AND approved=TRUE ORDER BY shot_order,asset_id""", (session_id,))
            ordered = [int(item["asset_id"]) for item in cursor.fetchall()]
            cursor.execute("""UPDATE public.photoshoot_commerce_deliverables SET
                ordered_member_asset_ids=%s::jsonb,shot_count=%s,hero_asset_id=%s,
                commerce_status='CURATED',updated_at=NOW() WHERE deliverable_id=%s""",
                (json.dumps(ordered), len(ordered), teaser_asset_id, intent["deliverable_id"]))
            relationship_id = uuid4()
            cursor.execute("""INSERT INTO public.asset_lineage_relationships
                (relationship_id,source_asset_id,derived_asset_id,source_position,derivation_kind,provenance)
                VALUES(%s,%s,%s,0,%s,%s::jsonb)""",
                (relationship_id, intent["source_asset_id"], teaser_asset_id,
                 DerivationKind.IMAGE_EDIT.value, json.dumps({"purpose": self.PURPOSE,
                 "intent_id": str(intent["intent_id"]), "origin_deliverable_id": str(intent["deliverable_id"])})))
            cursor.execute("""INSERT INTO public.generation_image_dispositions(image_id,owner,owner_id)
                VALUES(%s,'PHOTOSHOOT',%s) ON CONFLICT(image_id) DO UPDATE SET
                owner=EXCLUDED.owner,owner_id=EXCLUDED.owner_id,updated_at=NOW()""",
                (candidate_image_id, intent["deliverable_id"]))
            cursor.execute("""UPDATE public.photoshoot_session_teaser_edit_intents SET
                status='COMPLETED',result_image_id=%s,teaser_asset_id=%s,completed_at=NOW()
                WHERE intent_id=%s AND status='ACTIVE'""",
                (candidate_image_id, teaser_asset_id, intent["intent_id"]))
            if cursor.rowcount != 1:
                raise ValueError("Session teaser edit intent changed before completion.")
        return {"success": True, "deliverableId": str(intent["deliverable_id"]),
                "teaserAssetId": teaser_asset_id, "memberAssetIds": ordered,
                "message": "Teaser added as Shot 1. Existing shots shifted forward." if not old_teaser
                else "Session teaser replaced. Paid shot order was preserved."}

    @staticmethod
    def _eligibility(row):
        if not row: return False, "Photoshoot not found."
        if row["is_archived"] or not row["is_active"]: return False, "Archived or inactive Photoshoots cannot be changed."
        if str(row.get("selling_mode") or "SESSION") != "SESSION": return False, "Create Teaser is available only for Session Photoshoots."
        if row.get("registration_state") == "ARCHIVED": return False, "Archived Photoshoots cannot be changed."
        blockers = ("strategy_count", "offering_count", "publication_count", "intent_count", "purchase_count", "lifecycle_count")
        if any(int(row.get(key) or 0) for key in blockers):
            return False, "This Photoshoot already has commercial preparation or customer activity."
        return True, None

    @staticmethod
    def _locked_context(cursor, deliverable_id, creator_profile_id, *, lock):
        cursor.execute(f"""SELECT d.*,
          first_member.asset_id AS source_asset_id,
          completed.teaser_asset_id AS existing_teaser_asset_id,
          (SELECT COUNT(*) FROM public.photoshoot_session_sales_strategies s WHERE s.photoshoot_session_id=d.photoshoot_session_id) strategy_count,
          (SELECT COUNT(*) FROM public.commercial_offerings o WHERE o.source_photoshoot_deliverable_id=d.deliverable_id AND o.status<>'ARCHIVED') offering_count,
          (SELECT COUNT(*) FROM public.commercial_publications p JOIN public.commercial_offerings o ON o.offering_id=p.commercial_offering_id WHERE o.source_photoshoot_deliverable_id=d.deliverable_id) publication_count,
          (SELECT COUNT(*) FROM public.purchase_intents i JOIN public.commercial_offerings o ON o.offering_id=i.commercial_offering_id WHERE o.source_photoshoot_deliverable_id=d.deliverable_id) intent_count,
          (SELECT COUNT(*) FROM public.purchase_intents i JOIN public.commercial_offerings o ON o.offering_id=i.commercial_offering_id WHERE o.source_photoshoot_deliverable_id=d.deliverable_id AND (i.purchased_at IS NOT NULL OR i.status='PURCHASED')) purchase_count,
          (SELECT COUNT(*) FROM public.customer_photoshoot_lifecycles l WHERE l.photoshoot_id=d.photoshoot_session_id AND l.creator_profile_id=d.creator_profile_id) lifecycle_count
        FROM public.photoshoot_commerce_deliverables d
        JOIN public.photoshoot_asset_memberships first_member ON first_member.photoshoot_session_id=d.photoshoot_session_id AND first_member.shot_order=1 AND first_member.approved=TRUE
        LEFT JOIN LATERAL (SELECT teaser_asset_id FROM public.photoshoot_session_teaser_edit_intents i WHERE i.deliverable_id=d.deliverable_id AND i.status='COMPLETED' AND i.teaser_asset_id=first_member.asset_id ORDER BY i.completed_at DESC LIMIT 1) completed ON TRUE
        WHERE d.deliverable_id=%s AND d.creator_profile_id=%s {'FOR UPDATE OF d' if lock else ''}""",
        (deliverable_id, creator_profile_id))
        row = cursor.fetchone()
        return dict(row) if row else None
