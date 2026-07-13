from datetime import datetime
from pathlib import Path
import base64
import json
import mimetypes
import re

import streamlit as st

from app.models.creator_approval import ApprovedSourceIdentity, CreatorApprovalRequest
from app.models.creator_intent import CreatorIntent
from app.services.ai_import_workflow_service import AIImportWorkflowService
from app.services.creator_approval_service import CreatorApprovalService
from app.services.creator_review_service import CreatorReviewService
from app.services.grok_caption_service import GrokCaptionService
from app.services.publishing_service import PublishingService


CONFIG_PATH = Path("data/config/behavior_config.json")
_PUBLISHING_SERVICE = PublishingService()
_AI_IMPORT_WORKFLOW = AIImportWorkflowService()
_CREATOR_APPROVAL_SERVICE = CreatorApprovalService()
_CREATOR_REVIEW_SERVICE = CreatorReviewService()
IMAGE_UPLOAD_TYPES = ["jpg", "jpeg", "png", "webp"]
VIDEO_UPLOAD_TYPES = ["mp4", "mov", "webm", "m4v"]
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}


def _load_behavior_config() -> dict:
    try:
        if not CONFIG_PATH.exists():
            return {}

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}


def _is_mass_ppv_enabled() -> bool:
    """
    Reads Mass PPV toggle from:
    1. st.session_state
    2. data/config/behavior_config.json -> modules.mass_ppv_enabled
    3. data/config/behavior_config.json -> mass_ppv_enabled
    """

    if "mass_ppv_enabled" in st.session_state:
        return bool(st.session_state["mass_ppv_enabled"])

    config = _load_behavior_config()
    modules = config.get("modules", {})

    if "mass_ppv_enabled" in modules:
        return bool(modules.get("mass_ppv_enabled"))

    if "mass_ppv_enabled" in config:
        return bool(config.get("mass_ppv_enabled"))

    return True


def _file_to_data_url(file_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(file_path))

    if not mime_type:
        mime_type = "image/jpeg"

    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{encoded}"


def _normalize_captions(raw_response) -> list[str]:
    if not raw_response:
        return []

    if isinstance(raw_response, list):
        return [str(c).strip() for c in raw_response if str(c).strip()]

    if isinstance(raw_response, dict):
        possible = (
            raw_response.get("captions")
            or raw_response.get("caption_options")
            or raw_response.get("results")
            or raw_response.get("data")
        )

        if isinstance(possible, list):
            return [str(c).strip() for c in possible if str(c).strip()]

        if isinstance(possible, str):
            raw_response = possible
        else:
            return []

    if isinstance(raw_response, str):
        text = raw_response.strip()

        try:
            parsed = json.loads(text)
            return _normalize_captions(parsed)
        except Exception:
            pass

        cleaned = []

        for line in text.splitlines():
            line = line.strip()

            if not line:
                continue

            line = re.sub(r"^\d+[\).\-\s]+", "", line).strip()
            line = line.strip('"').strip("'").strip()

            if line:
                cleaned.append(line)

        return cleaned if cleaned else [text]

    return []


def _format_price(cents) -> str:
    if cents is None:
        return "Not set"
    return f"${int(cents) / 100:.2f}"


def _is_video_path(file_path: Path) -> bool:
    return file_path.suffix.lower() in VIDEO_SUFFIXES


def _upload_intent_for_media(upload_intent: str, file_path: Path) -> str:
    if not _is_video_path(file_path):
        return upload_intent

    intent = (upload_intent or "").lower()
    if intent.endswith("_image"):
        return f"{intent[:-6]}_video"
    if intent.endswith("_video"):
        return intent
    return "teaser_video"


def _creator_intent_from_selection(
    content_structure: str,
    *,
    upload_intent: str,
    notes: str | None = None,
) -> CreatorIntent:
    content_type = (
        "PHOTOSHOOT"
        if str(content_structure or "").strip().lower() == "photo set"
        else "SINGLE_ASSET"
    )
    return CreatorIntent.create(
        content_type,
        legacy_upload_intent=upload_intent,
        confirmed=True,
        override_active=True,
        notes=notes,
        metadata={
            "source": "cms_upload",
            "content_structure": content_structure,
        },
    )


def _promote_manual_upload(
    *,
    asset_id: int | None,
    media_reference: str | Path,
    original_filename: str | None,
    creator_profile_id: int | None,
    creator_intent: CreatorIntent,
    source_metadata: dict,
) -> None:
    if asset_id is None:
        return
    request = CreatorApprovalRequest(
        source=ApprovedSourceIdentity(
            source_workflow="cms_upload",
            source_item_id=str(asset_id),
            source_session_id=source_metadata.get("classification_key"),
            idempotency_key=f"cms-upload:{asset_id}",
        ),
        media_reference=str(media_reference),
        creator_profile_id=creator_profile_id,
        creator_intent=creator_intent,
        source_metadata={
            "original_filename": original_filename,
            "approval_entrypoint": "cms_upload_manual_import",
            **dict(source_metadata or {}),
        },
    )
    _CREATOR_APPROVAL_SERVICE.promote_existing_asset(
        int(asset_id),
        request,
        asset_repository=_AI_IMPORT_WORKFLOW.assets,
    )


def _render_staged_media(file_path: Path, *, width: int, caption: str | None = None) -> None:
    if _is_video_path(file_path):
        st.video(str(file_path))
        if caption:
            st.caption(caption)
        return
    st.image(str(file_path), width=width, caption=caption)


def _render_product_result_summary(
    *,
    classification: str | None,
    tags,
    themes,
    product_id: str | None = None,
    product_type: str | None = None,
    price_cents=None,
    base_price_cents=None,
    min_price_cents=None,
    max_price_cents=None,
    activation_status: str | None = None,
):
    st.markdown("### Asset Result")
    c1, c2 = st.columns(2)
    c1.success("Preview")
    c2.success("Classification")
    st.write(classification or "Pending")

    c3, c4 = st.columns(2)
    c3.success("Tags")
    c3.write(tags or [])
    c4.success("Themes")
    c4.write(themes or [])

    p1, p2, p3 = st.columns(3)
    p1.success("Product Created")
    p1.write(product_id or "Pending")
    p2.success("Product Type")
    p2.write(product_type or "Pending")
    p3.success("Activation Status")
    p3.write(activation_status or "Pending")

    st.success("Pricing")
    st.write(
        {
            "price": _format_price(price_cents),
            "base": _format_price(base_price_cents),
            "min": _format_price(min_price_cents),
            "max": _format_price(max_price_cents),
        }
    )


def _format_confidence(confidence) -> str:
    if confidence is None:
        return "Not available"
    try:
        return f"{float(confidence) * 100:.0f}%"
    except (TypeError, ValueError):
        return str(confidence)


def _compact_mapping(data: dict) -> dict:
    return {
        key: value
        for key, value in (data or {}).items()
        if value not in (None, (), [], {})
    }


def _render_creator_review_section(section) -> None:
    label = section.title
    status = section.status or "available"
    with st.expander(f"{label} - {status}", expanded=False):
        if section.summary:
            st.write(section.summary)
        if section.confidence is not None:
            st.caption(f"Confidence: {_format_confidence(section.confidence)}")
        data = _compact_mapping(dict(section.data or {}))
        if data:
            st.write(data)
        if section.evidence:
            st.caption("Evidence")
            st.write(list(section.evidence))
        for warning in section.warnings:
            st.warning(warning)


def _render_creator_review(review) -> None:
    if not review:
        return

    st.markdown("### Creator Review")
    st.caption(
        "AI import results are ready for creator review. "
        "Manual overrides are review-only in this phase."
    )

    if review.warnings:
        for warning in review.warnings:
            st.warning(warning)

    experience_overrides = {}
    experience_data = dict(review.experience.data or {})
    supported_overrides = tuple(
        experience_data.get("supported_overrides", ()) or ()
    )
    if supported_overrides:
        with st.expander("Experience Override Proposals", expanded=False):
            st.caption("These proposals are review-only and are not saved.")
            if "experience_name" in supported_overrides:
                experience_overrides["experience_name"] = st.text_input(
                    "Experience Name",
                    value=experience_data.get("experience_name") or "",
                    key=f"creator_review_experience_name_{review.review_type}_{review.asset_ids}",
                )
            if "experience_summary" in supported_overrides:
                experience_overrides["experience_summary"] = st.text_area(
                    "Experience Summary",
                    value=experience_data.get("experience_summary") or "",
                    key=f"creator_review_experience_summary_{review.review_type}_{review.asset_ids}",
                )
            if "cover_asset_id" in supported_overrides:
                experience_overrides["cover_asset_id"] = st.text_input(
                    "Cover Asset ID",
                    value=str(experience_data.get("cover_asset_id") or ""),
                    key=f"creator_review_cover_asset_{review.review_type}_{review.asset_ids}",
                )
            if "themes" in supported_overrides:
                experience_overrides["themes"] = st.text_input(
                    "Themes",
                    value=", ".join(experience_data.get("themes") or ()),
                    key=f"creator_review_themes_{review.review_type}_{review.asset_ids}",
                )
            if "keywords" in supported_overrides:
                experience_overrides["keywords"] = st.text_input(
                    "Keywords",
                    value=", ".join(experience_data.get("keywords") or ()),
                    key=f"creator_review_keywords_{review.review_type}_{review.asset_ids}",
                )
            st.caption("Override proposals")
            st.write(_compact_mapping(experience_overrides))

    sections = (
        review.asset,
        review.asset_understanding,
        review.content_intelligence,
        review.experience,
        review.experience_recommendation,
        review.product_strategy,
        review.commerce_strategy,
        review.commerce_recommendation,
        review.product_draft,
        review.delivery_type,
        review.publishing_readiness,
        review.organization,
    )
    for section in sections:
        _render_creator_review_section(section)

    if review.manual_overrides:
        st.caption("Manual override proposals")
        st.write(dict(review.manual_overrides))


def render_cms_upload():

    active_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    active_account = (
        st.session_state.get(
            "active_fanvue_account",
            {}
        )
    )

    creator_profile = st.session_state.get(
        "active_creator_profile",
    )

    if not creator_profile:
        st.error(
            "Creator Profile required before using Asset Ingestion."
        )
        st.stop()

    st.subheader("Asset Ingestion")

    grok_service = GrokCaptionService()
    content_structure = st.radio(
        "Asset Package",
        [
            "Single Image",
            "Photo Set",
        ],
        index=0,
        horizontal=True,
        help=(
            "Single Image keeps the existing 1 image -> 1 Asset -> 1 Product "
            "flow. Photo Set creates one ordered PHOTO_SET Product from all "
            "uploaded images."
        ),
    )
    # Hidden for the simplified ingestion page. Import remains local by
    # default; provider publishing workflows are handled separately.
    upload_workflow = "Local Asset Only"
    fanvue_upload_enabled = upload_workflow == "Local Asset + Provider Upload"

    # Hidden for now; keep the mapping so the previous Upload Intent control
    # can be restored without touching the ingestion pipeline.
    upload_intent_label = "Teaser Image"

    intent_map = {
        "Teaser Image": "teaser_image",
        "Teaser Video": "teaser_video",
        "Wall Image": "wall_image",
        "Wall Video": "wall_video",
        "PPV Image": "ppv_image",
        "PPV Video": "ppv_video",
    }

    selected_upload_intent = intent_map[upload_intent_label]
    selected_creator_intent = _creator_intent_from_selection(
        content_structure,
        upload_intent=selected_upload_intent,
    )

    # Hidden for the simplified ingestion page. Restore this section when
    # advanced Mass PPV/content routing controls are needed again.

    mass_ppv_enabled = _is_mass_ppv_enabled()

    if False and not mass_ppv_enabled:
        st.warning(
            "⚠️ Mass PPV is currently disabled. You can still upload and store content, "
            "but the Mass PPV system will not send it until Mass PPV is enabled."
        )

    # Previous UI: st.selectbox("Content Tier", ["TEASE", "VIP", "PREMIUM"])
    content_tier = "VIP"

    # Previous UI: st.selectbox("Distribution Type", ["one_on_one", "mass_ppv", "both"])
    distribution_type = "both"

    # Previous UI: st.number_input("Mass PPV Base Price", value=14.99)
    mass_ppv_price = 14.99

    uploaded_files = st.file_uploader(
        "Import Assets",
        type=IMAGE_UPLOAD_TYPES + VIDEO_UPLOAD_TYPES,
        accept_multiple_files=True,
    )

    # Phase 1 compatibility: data/uploads is an import staging area.
    # AssetIngestionService copies successful imports into the Local Vault.
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    if not uploaded_files:
        return

    if content_structure == "Photo Set":
        if len(uploaded_files) < 2:
            st.warning("Photo Set requires at least two uploaded images.")
            return

        photo_set_key = (
            "photo_set_"
            f"{selected_upload_intent}_{upload_workflow}_"
            + "_".join(
                f"{uploaded_file.name}_{uploaded_file.size}"
                for uploaded_file in uploaded_files
            )
        )
        photo_set_review_key = f"{photo_set_key}_creator_review"

        if photo_set_key in st.session_state:
            photo_set_result = st.session_state[photo_set_key]
            st.success("Photo Set already processed in this dashboard session.")
            _render_creator_review(st.session_state.get(photo_set_review_key))
            st.write(photo_set_result)
            return

        st.markdown("### Photo Set Asset Preview")
        media_items = []

        for position, uploaded_file in enumerate(uploaded_files):
            if Path(uploaded_file.name).suffix.lower() in VIDEO_SUFFIXES:
                st.warning("Photo Set currently supports images only.")
                return

            stable_file_key = uploaded_file.name.replace(" ", "_")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{timestamp}_{position:03d}_{stable_file_key}"
            file_path = upload_dir / filename

            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            _render_staged_media(
                file_path,
                width=180,
                caption=f"{position + 1}. {uploaded_file.name}",
            )

            media_upload_intent = _upload_intent_for_media(
                selected_upload_intent,
                file_path,
            )
            media_items.append(
                {
                    "media_path": file_path,
                    "original_filename": uploaded_file.name,
                    "upload_intent": media_upload_intent,
                }
            )

        try:
            batch_result = _AI_IMPORT_WORKFLOW.import_asset_batch(
                media_items=media_items,
                upload_intent=selected_upload_intent,
                creator_intent=selected_creator_intent,
                creator_profile_id=creator_profile.get("id"),
                fanvue_account_id=active_account_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=float(mass_ppv_price),
                package_type="photo_set",
                create_product_draft=True,
                provider_upload_enabled=False,
                is_test=False,
            )
        except Exception as error:
            st.exception(error)
            return

        classification_results = list(batch_result.legacy_results)
        content_ids = list(batch_result.content_ids)
        creator_review = _CREATOR_REVIEW_SERVICE.build_review(batch_result)
        st.session_state[photo_set_review_key] = creator_review

        for asset_result, result in zip(
            batch_result.asset_results,
            classification_results,
        ):
            vision = result.get("gpt_vision_raw", {}) or {}
            st.caption(
                f"Asset #{asset_result.content_id}: "
                f"{result.get('final_classification')} | "
                f"confidence={vision.get('confidence')}"
            )

        if not batch_result.success:
            st.error(
                "Photo Set asset creation did not complete for every imported image."
            )
            _render_creator_review(creator_review)
            st.write(classification_results)
            return

        photo_set = batch_result.product_draft_result
        if not photo_set:
            st.error("Photo Set Product creation did not complete.")
            _render_creator_review(creator_review)
            st.write(classification_results)
            return

        photo_set_result = {
            "success": True,
            "asset_ids": content_ids,
            "product_id": str(photo_set.product.id),
            "product_type": photo_set.product.product_type.value,
            "status": photo_set.product.status.value,
            "activated": photo_set.activated,
            "price_cents": photo_set.product.price_cents,
            "base_price_cents": photo_set.product.base_price_cents,
            "min_price_cents": photo_set.product.min_price_cents,
            "max_price_cents": photo_set.product.max_price_cents,
            "asset_count": len(content_ids),
        }
        st.session_state[photo_set_key] = photo_set_result

        st.toast("Saved Photo Set as one Product")
        st.success(
            f"Created {len(content_ids)} Assets and one "
            f"{photo_set.product.status.value} PHOTO_SET Product."
        )
        _render_creator_review(creator_review)
        first_result = classification_results[0] if classification_results else {}
        first_vision = first_result.get("gpt_vision_raw", {}) or {}
        _render_product_result_summary(
            classification=first_result.get("final_classification"),
            tags=first_vision.get("suggested_tags"),
            themes=first_vision.get("detected_themes"),
            product_id=str(photo_set.product.id),
            product_type=photo_set.product.product_type.value,
            price_cents=photo_set.product.price_cents,
            base_price_cents=photo_set.product.base_price_cents,
            min_price_cents=photo_set.product.min_price_cents,
            max_price_cents=photo_set.product.max_price_cents,
            activation_status=photo_set.product.status.value,
        )
        st.write(photo_set_result)
        return

    for uploaded_file in uploaded_files:
        stable_file_key = uploaded_file.name.replace(" ", "_")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}_{stable_file_key}"
        file_path = upload_dir / filename

        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        _render_staged_media(file_path, width=250)

        media_upload_intent = _upload_intent_for_media(
            selected_upload_intent,
            file_path,
        )
        workflow_key = "fanvue" if fanvue_upload_enabled else "local"
        classification_key = (
            f"classification_{stable_file_key}_{media_upload_intent}_{workflow_key}"
        )
        fanvue_upload_key = (
            f"fanvue_upload_{stable_file_key}_{media_upload_intent}_{workflow_key}"
        )
        creator_review_key = (
            f"creator_review_{stable_file_key}_{media_upload_intent}_{workflow_key}"
        )

        if classification_key not in st.session_state:
            selected_creator_intent = _creator_intent_from_selection(
                content_structure,
                upload_intent=media_upload_intent,
            )
            import_result = _AI_IMPORT_WORKFLOW.import_asset(
                media_path=file_path,
                upload_intent=media_upload_intent,
                creator_intent=selected_creator_intent,
                creator_profile_id=creator_profile.get("id"),
                original_filename=uploaded_file.name,
                fanvue_account_id=active_account_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=float(mass_ppv_price),
                create_product_draft=True,
                provider_upload_enabled=False,
                is_test=False,
            )
            _promote_manual_upload(
                asset_id=import_result.content_id,
                media_reference=file_path,
                original_filename=uploaded_file.name,
                creator_profile_id=creator_profile.get("id"),
                creator_intent=selected_creator_intent,
                source_metadata={
                    "classification_key": classification_key,
                    "upload_intent": media_upload_intent,
                    "content_structure": content_structure,
                },
            )
            result = import_result.to_legacy_result()
            creator_review = _CREATOR_REVIEW_SERVICE.build_review(import_result)

            st.session_state[classification_key] = result
            st.session_state[creator_review_key] = creator_review

            if fanvue_upload_enabled:
                upload_result = _PUBLISHING_SERVICE.upload_asset_media_item(
                    fanvue_account_id=active_account_id,
                    item={
                        "file_path": str(file_path),
                        "classification": media_upload_intent.upper(),
                    },
                )
            else:
                upload_result = {
                    "success": True,
                    "skipped": True,
                    "status": "not_requested",
                    "reason": "local_asset_only",
                }

            st.session_state[fanvue_upload_key] = upload_result

            if upload_result.get("skipped"):
                st.toast(
                    "Saved local Asset + created Product Draft",
                )
                st.success(
                    "Saved local Asset. Publishing was not required."
                )
                st.caption(f"Stored as: {result.get('final_classification')}")

            elif upload_result.get("success") and upload_result.get("folder_success"):
                folder_name = upload_result.get("folder_name") or "selected"

                st.toast(
                    f"✅ Saved to CMS + uploaded to provider {folder_name} folder",
                )

                st.success(
                    f"Saved to CMS database and uploaded to provider {folder_name} folder ✅"
                )

                st.caption(f"📦 Stored as: {result.get('final_classification')}")
                st.caption(f"🗂️ Provider folder: {folder_name}")

            else:
                st.error("CMS save completed, but provider upload/folder routing failed.")
                st.write(upload_result)

        else:
            result = st.session_state[classification_key]
            upload_result = st.session_state.get(fanvue_upload_key)
            creator_review = st.session_state.get(creator_review_key)

            if upload_result and upload_result.get("skipped"):
                st.caption("✅ Already saved as a local Asset.")
            elif upload_result and upload_result.get("success") and upload_result.get("folder_success"):
                folder_name = upload_result.get("folder_name") or "selected"
                st.caption(f"✅ Already saved + uploaded to provider {folder_name} folder")
            elif upload_result:
                st.warning("Previous provider upload/folder routing did not complete.")
                st.write(upload_result)

        vision = result.get("gpt_vision_raw", {}) or {}
        product_result = (
            (result.get("db_save_result") or {}).get("product_draft_result")
            or {}
        )
        _render_product_result_summary(
            classification=result.get("final_classification"),
            tags=vision.get("suggested_tags"),
            themes=vision.get("detected_themes"),
            product_id=product_result.get("product_id"),
            product_type=product_result.get("product_type"),
            price_cents=product_result.get("price_cents"),
            base_price_cents=product_result.get("base_price_cents"),
            min_price_cents=product_result.get("min_price_cents"),
            max_price_cents=product_result.get("max_price_cents"),
            activation_status=product_result.get("status"),
        )
        _render_creator_review(creator_review)

        # =========================================
        # WALL CAPTIONS — ONLY FOR WALL CONTENT
        # =========================================
        if media_upload_intent in ["wall_image", "wall_video"]:

            st.markdown("### ✨ Generate Wall Captions")

            content_metadata = {
                "classification": result.get("final_classification"),
                "tags": vision.get("suggested_tags", []),
                "themes": vision.get("detected_themes", []),
                "summary": vision.get("short_safe_summary", ""),
            }

            caption_key = f"captions_{stable_file_key}"

            if st.button(
                "🔥 Generate Captions with Grok",
                key=f"generate_captions_{stable_file_key}",
                use_container_width=True,
            ):
                with st.spinner("Generating captions... 🔥"):
                    image_url = _file_to_data_url(file_path)

                    raw = grok_service.generate_wall_captions(
                        content_metadata=content_metadata,
                        image_url=image_url,
                    )

                    captions = _normalize_captions(raw)
                    st.session_state[caption_key] = captions

                    st.session_state.pop(f"radio_{stable_file_key}", None)

            captions = st.session_state.get(caption_key, [])

            if captions:
                st.success("5 captions generated!")

                selected = st.radio(
                    "Pick your caption:",
                    captions,
                    index=0,
                    key=f"radio_{stable_file_key}",
                )

                st.markdown(f"""
                <div style="
                    margin-top: 18px;
                    padding: 16px 18px;
                    border-radius: 14px;
                    background: linear-gradient(135deg, rgba(255,78,205,0.18), rgba(122,92,255,0.18));
                    border: 1px solid rgba(255,78,205,0.45);
                    box-shadow: 0 0 18px rgba(255,78,205,0.12);
                ">
                    <div style="
                        font-size: 0.9rem;
                        font-weight: 700;
                        color: #ff8be6;
                        margin-bottom: 8px;
                        text-transform: uppercase;
                        letter-spacing: 0.04em;
                    ">
                        ✨ Selected Caption
                    </div>
                    <div style="
                        font-size: 1.05rem;
                        line-height: 1.55;
                        color: white;
                        font-weight: 500;
                    ">
                        {selected}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                wall_action = st.radio(
                    "What do you want to do?",
                    ["Post Now", "Add to Wall Scheduler"],
                    key=f"wall_action_{stable_file_key}",
                    horizontal=True,
                )

                if wall_action == "Post Now":
                    if st.button(
                        "🚀 Post Now",
                        key=f"post_now_{stable_file_key}",
                        use_container_width=True,
                    ):
                        with st.spinner("Posting to provider wall... 🚀"):
                            try:
                                upload_result = st.session_state.get(fanvue_upload_key)

                                if upload_result and upload_result.get("skipped"):
                                    st.error(
                                        "This asset was saved locally only. "
                                        "Choose 'Local Asset + Provider Upload' "
                                        "if you want to post it to the provider."
                                    )
                                    st.write(upload_result)
                                elif not upload_result or not upload_result.get("success"):
                                    st.error("Cannot post. Provider media upload/folder routing was not successful.")
                                    st.write(upload_result)
                                else:
                                    media_uuid = (
                                        upload_result.get("media_uuid")
                                        or upload_result.get("full_uuid")
                                        or upload_result.get("preview_uuid")
                                    )

                                    if not media_uuid:
                                        st.error("Upload succeeded, but no media UUID was returned.")
                                        st.write(upload_result)
                                    else:
                                        post_result = _PUBLISHING_SERVICE.create_wall_post(
                                            fanvue_account_id=active_account_id,
                                            text=selected,
                                            media_ids=[media_uuid],
                                            audience="followers-and-subscribers",
                                        )

                                        if post_result.get("success"):
                                            st.success("Posted to provider wall successfully ✅")
                                            st.write(post_result)
                                        else:
                                            st.error("Provider wall post failed.")
                                            st.write(post_result)

                            except Exception as e:
                                st.error(f"Post Now failed: {e}")

                else:
                    if st.button(
                        "🗓️ Add to Wall Scheduler",
                        key=f"schedule_wall_{stable_file_key}",
                        use_container_width=True,
                    ):
                        st.session_state[f"scheduled_wall_caption_{stable_file_key}"] = {
                            "fanvue_account_id": active_account_id,
                            "caption": selected,
                            "file_path": str(file_path),
                            "media_uuid": (
                                st.session_state.get(fanvue_upload_key, {}).get("media_uuid")
                                if st.session_state.get(fanvue_upload_key)
                                else None
                            ),
                            "status": "pending_scheduler",
                        }

                        st.success("Added to Wall Scheduler queue ✅")

            else:
                st.warning("No captions yet — click the button above.")

        st.divider()
