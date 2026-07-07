import base64
import json
import mimetypes
from pathlib import Path

from dotenv import load_dotenv
from nudenet import NudeDetector
from openai import OpenAI

from app.repositories.content_repository import (
    insert_content_item,
)
from app.services.publishing_service import PublishingService


load_dotenv()

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

client = OpenAI()
detector = NudeDetector()
_PUBLISHING_SERVICE = PublishingService()

_ANALYSIS_MODEL = "gpt-4.1-mini"
_ANALYSIS_VERSION = "phase_2c_ai_product_drafting_v1"


def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_image_mime_type(image_path: Path) -> str:
    ext = image_path.suffix.lower()

    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"

    if ext == ".png":
        return "image/png"

    if ext == ".webp":
        return "image/webp"

    return "image/jpeg"


def build_media_metadata(media_path: Path) -> dict:
    try:
        stat = media_path.stat()
        size_bytes = stat.st_size
    except OSError:
        size_bytes = None

    mime_type, _ = mimetypes.guess_type(str(media_path))
    return {
        "file_extension": media_path.suffix.lower(),
        "mime_type": mime_type,
        "size_bytes": size_bytes,
    }


def build_analysis_provenance(upload_intent: str) -> dict:
    return {
        "source": "cms_upload",
        "analysis_version": _ANALYSIS_VERSION,
        "vision_model": _ANALYSIS_MODEL,
        "nudenet_enabled": upload_intent == "ppv_image",
        "upload_intent": upload_intent,
    }


def add_context_to_payload(
    payload: dict,
    *,
    image_path: Path,
    upload_intent: str,
    gpt_result_raw: dict | None = None,
    nudenet_result: list | None = None,
    final_result: dict | None = None,
    fanvue_account_id: int | None = None,
    creator_profile_id: int | None = None,
    content_tier: str | None = None,
    distribution_type: str | None = None,
    mass_ppv_price: float | None = None,
    fanvue_upload_enabled: bool | None = None,
    original_filename: str | None = None,
) -> dict:
    gpt_result_raw = gpt_result_raw or {}
    nudenet_result = nudenet_result or []
    final_result = final_result or {}

    media_metadata = build_media_metadata(image_path)
    media_metadata["original_filename"] = original_filename or image_path.name

    payload.update(
        {
            "fanvue_account_id": fanvue_account_id,
            "creator_profile_id": creator_profile_id,
            "content_tier": content_tier,
            "distribution_type": distribution_type,
            "mass_ppv_price": mass_ppv_price,
            "short_safe_summary": gpt_result_raw.get("short_safe_summary"),
            "risk_flags": gpt_result_raw.get("risk_flags", []),
            "analysis_reasoning": gpt_result_raw.get("reasoning"),
            "analysis_provenance": build_analysis_provenance(upload_intent),
            "media_metadata": media_metadata,
            "gpt_vision_result": gpt_result_raw,
            "nudenet_result": nudenet_result,
            "classification_result": final_result,
        }
    )
    if fanvue_upload_enabled is not None:
        payload["fanvue_upload_status"] = (
            "pending" if fanvue_upload_enabled else "not_requested"
        )
    return payload


def create_ai_product_draft_for_content(
    content_id: int | None,
    creator_profile_id: int | None,
) -> dict:
    if not content_id or not creator_profile_id:
        return {
            "success": False,
            "created": False,
            "reason": "missing_content_or_creator_profile",
        }

    try:
        from app.services.ai_product_drafting_service import (
            AIProductDraftingService,
        )

        return AIProductDraftingService().create_draft_result_for_asset(
            content_id,
            creator_profile_id=creator_profile_id,
        )
    except Exception as error:
        return {
            "success": False,
            "created": False,
            "error": str(error),
        }


def run_nudenet(image_path: Path) -> list:
    try:
        return detector.detect(str(image_path))
    except Exception as e:
        return [{"error": str(e)}]


def run_gpt_vision(image_path: Path, upload_intent: str = "ppv_image") -> dict:
    image_base64 = encode_image_to_base64(image_path)
    mime_type = get_image_mime_type(image_path)

    upload_intent = (upload_intent or "ppv_image").lower()

    prompt = f"""
You are analyzing content for a Fanvue content management system.

UPLOAD INTENT: {upload_intent}

You must adapt your response based on the upload intent.

INTENT RULES:

If upload_intent is "wall_image" or "wall_video":
- This is PUBLIC WALL / FEED CONTENT.
- Describe it like a social media wall post.
- Do NOT mention VIP, PPV, premium, paid, locked, unlock, monetization, buyer tier, or sales funnel.
- Focus on visual vibe, outfit, setting, pose, mood, confidence, and social appeal.

If upload_intent is "teaser_image" or "teaser_video":
- This is TEASER / WARM-UP CONTENT.
- Describe it as suggestive teaser content.
- Do NOT mention VIP, PPV, premium, paid, locked, unlock, or pricing.
- Focus on curiosity, attraction, outfit, pose, and visual hook.

If upload_intent is "ppv_image" or "ppv_video":
- This is PAID CONTENT CATALOGING.
- You may classify by monetization tier.
- You may mention VIP or premium suitability when appropriate.

CLASS OPTIONS:

TEASE:
- Suggestive but holding back
- Covered lingerie, cleavage, teasing poses, implied nudity

VIP:
- Topless content
- Partial nudity
- Strong reveal but not full explicit content

PREMIUM:
- Bottomless nudity
- Exposed genitalia
- Explicit sexual posing
- Sex acts

EDGE_CASE:
- Unclear or requires manual review

IMPORTANT:
- Return ONLY JSON.
- The short_safe_summary must obey the upload intent rules.
- Never call wall content VIP, PPV, premium, paid, locked, or unlocked.
"""

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_type};base64,{image_base64}",
                        },
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "fanvue_content_classification",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "classification": {
                                "type": "string",
                                "enum": ["TEASE", "VIP", "PREMIUM", "EDGE_CASE"],
                            },
                            "confidence": {"type": "number"},
                            "detected_themes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "suggested_tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "risk_flags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "short_safe_summary": {"type": "string"},
                            "reasoning": {"type": "string"},
                        },
                        "required": [
                            "classification",
                            "confidence",
                            "detected_themes",
                            "suggested_tags",
                            "risk_flags",
                            "short_safe_summary",
                            "reasoning",
                        ],
                    },
                    "strict": True,
                }
            },
        )

        return json.loads(response.output_text)

    except Exception as e:
        return {"error": str(e)}


def get_nudenet_labels(nudenet_result: list) -> list[str]:
    labels = []

    for item in nudenet_result:
        if isinstance(item, dict):
            label = item.get("class")
            if label:
                labels.append(label)

    return labels


def apply_tier_rules(gpt_result: dict, nudenet_result: list) -> dict:
    labels = get_nudenet_labels(nudenet_result)

    final_result = dict(gpt_result)
    raw_classification = final_result.get("classification", "EDGE_CASE")

    final_result["raw_gpt_classification"] = raw_classification
    final_result["final_classification"] = raw_classification
    final_result["rule_applied"] = None

    premium_labels = {
        "FEMALE_GENITALIA_EXPOSED",
        "MALE_GENITALIA_EXPOSED",
        "ANUS_EXPOSED",
    }

    vip_labels = {
        "FEMALE_BREAST_EXPOSED",
    }

    if any(label in premium_labels for label in labels):
        final_result["final_classification"] = "PREMIUM"
        final_result["rule_applied"] = "explicit_bottomless_or_genital_exposure_force_premium"

    elif any(label in vip_labels for label in labels):
        final_result["final_classification"] = "VIP"
        final_result["rule_applied"] = "topless_or_exposed_breast_force_vip"

    return final_result


def get_distribution_rules(final_classification: str) -> dict:
    rules = {
        "followers": {
            "allowed": False,
            "mode": "blocked",
            "reason": "Default blocked until classification is known.",
        },
        "subscribers": {
            "allowed": False,
            "mode": "blocked",
            "reason": "Default blocked until classification is known.",
        },
        "whales": {
            "allowed": False,
            "mode": "blocked",
            "reason": "Default blocked until classification is known.",
        },
    }

    if final_classification == "TEASE":
        rules["followers"] = {
            "allowed": True,
            "mode": "primary",
            "reason": "Safe funnel opener for followers.",
        }
        rules["subscribers"] = {
            "allowed": True,
            "mode": "supporting",
            "reason": "Can be used for light engagement or warm-up.",
        }
        rules["whales"] = {
            "allowed": True,
            "mode": "low_priority",
            "reason": "Usually too low-value for whales unless used conversationally.",
        }

    elif final_classification == "VIP":
        rules["followers"] = {
            "allowed": True,
            "mode": "limited",
            "reason": "Can be used sparingly as proof-of-value, not full access.",
        }
        rules["subscribers"] = {
            "allowed": True,
            "mode": "primary",
            "reason": "Core subscriber-value content, including topless/partial nudity.",
        }
        rules["whales"] = {
            "allowed": True,
            "mode": "supporting",
            "reason": "Can support upsell sequences before premium offers.",
        }

    elif final_classification == "PREMIUM":
        rules["followers"] = {
            "allowed": False,
            "mode": "blocked",
            "reason": "Premium explicit content should not be sent directly to followers.",
        }
        rules["subscribers"] = {
            "allowed": True,
            "mode": "paid_offer",
            "reason": "Primary paid PPV / premium upsell content.",
        }
        rules["whales"] = {
            "allowed": True,
            "mode": "high_value_paid_offer",
            "reason": "Best used for high-value buyers and whales.",
        }

    elif final_classification == "EDGE_CASE":
        rules["followers"] = {
            "allowed": False,
            "mode": "manual_review",
            "reason": "Needs manual review before distribution.",
        }
        rules["subscribers"] = {
            "allowed": False,
            "mode": "manual_review",
            "reason": "Needs manual review before distribution.",
        }
        rules["whales"] = {
            "allowed": False,
            "mode": "manual_review",
            "reason": "Needs manual review before distribution.",
        }

    return rules


def determine_nudity_level(nudenet_labels: list[str], final_classification: str) -> str:
    if final_classification == "PREMIUM":
        return "full"

    if "FEMALE_BREAST_EXPOSED" in nudenet_labels:
        return "partial"

    if any("COVERED" in label for label in nudenet_labels):
        return "covered"

    return "none"


def determine_sexual_intensity(final_classification: str) -> str:
    if final_classification == "PREMIUM":
        return "high"

    if final_classification == "VIP":
        return "medium"

    if final_classification == "TEASE":
        return "low"

    return "unknown"


def build_db_payload(
    image_path: Path,
    nudenet_result: list,
    gpt_result_raw: dict,
    final_result: dict,
    is_test: bool = False,
) -> dict:
    final_classification = final_result.get("final_classification", "EDGE_CASE")
    nudenet_labels = get_nudenet_labels(nudenet_result)

    return {
        "file_path": str(image_path),
        "file_name": image_path.name,
        "classification": final_classification,
        "confidence": gpt_result_raw.get("confidence"),
        "detected_themes": json.dumps(gpt_result_raw.get("detected_themes", [])),
        "suggested_tags": json.dumps(gpt_result_raw.get("suggested_tags", [])),
        "nudity_labels": json.dumps(nudenet_labels),
        "nudity_level": determine_nudity_level(nudenet_labels, final_classification),
        "sexual_intensity": determine_sexual_intensity(final_classification),
        "is_explicit": final_classification == "PREMIUM",
        "is_test": is_test,
    }


def classify_content_image(
    image_path: str | Path,
    save_to_db: bool = False,
    is_test: bool = False,
    upload_intent: str = "ppv_image",
    fanvue_account_id: int | None = None,
    creator_profile_id: int | None = None,
    content_tier: str | None = None,
    distribution_type: str | None = None,
    mass_ppv_price: float | None = None,
    fanvue_upload_enabled: bool = True,
    create_product_draft: bool = True,
    original_filename: str | None = None,
) -> dict:
    image_path = Path(image_path)

    if not image_path.exists():
        return {
            "success": False,
            "error": f"Image not found: {image_path}",
        }

    upload_intent = upload_intent.lower()

    # =========================================
    # 🔵 TEASER IMAGE — Vision only, auto-approved
    # =========================================
    if upload_intent == "teaser_image":
        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return {
                "success": False,
                "error": f"Unsupported image file type: {image_path.suffix}",
            }

        gpt_result_raw = run_gpt_vision(image_path, upload_intent)

        
        final_result = {
            "final_classification": "TEASE",
            "rule_applied": "forced_teaser_image",
            "raw_gpt_classification": gpt_result_raw.get("classification"),
        }

        distribution_rules = get_distribution_rules("TEASE")

        db_save_result = {
            "saved": False,
            "reason": "save_to_db_false",
        }

        if save_to_db:
            db_payload = build_db_payload(
                image_path=image_path,
                nudenet_result=[],
                gpt_result_raw=gpt_result_raw,
                final_result=final_result,
                is_test=is_test,
            )

            db_payload.update({
                "upload_intent": "teaser_image",
                "requires_nudenet": False,
                "requires_blur": False,
                "requires_vision": True,
                "status": "approved",
                "ready_for_rotation": True,
                "content_type": "teaser",
                "fanvue_upload_status": (
                    "pending" if fanvue_upload_enabled else "not_requested"
                ),
            })
            add_context_to_payload(
                db_payload,
                image_path=image_path,
                upload_intent="teaser_image",
                gpt_result_raw=gpt_result_raw,
                nudenet_result=[],
                final_result=final_result,
                fanvue_account_id=fanvue_account_id,
                creator_profile_id=creator_profile_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=mass_ppv_price,
                fanvue_upload_enabled=fanvue_upload_enabled,
                original_filename=original_filename,
            )

            content_id = insert_content_item(db_payload)
            product_draft_result = (
                create_ai_product_draft_for_content(
                    content_id,
                    creator_profile_id,
                )
                if create_product_draft
                else {
                    "success": True,
                    "created": False,
                    "reason": "product_draft_deferred",
                }
            )

            upload_result = None

            if fanvue_upload_enabled:
                try:
                    upload_result = _PUBLISHING_SERVICE.upload_asset_media_item(
                        fanvue_account_id=fanvue_account_id,
                        item={
                            "id": content_id,
                            "file_path": db_payload["file_path"],
                            "classification": db_payload["classification"],
                        },
                    )

                    if upload_result.get("success"):
                        payload = _PUBLISHING_SERVICE.build_provider_status_update(
                            provider_status="completed",
                            provider_metadata={},
                        )
                        payload.update(
                            {
                                "provider_preview_media_id": upload_result.get(
                                    "preview_uuid"
                                ),
                                "provider_full_media_id": upload_result.get(
                                    "full_uuid"
                                ),
                            }
                        )
                    else:
                        payload = _PUBLISHING_SERVICE.build_provider_status_update(
                            provider_status="failed",
                            provider_error=str(upload_result.get("error")),
                            provider_metadata={},
                        )
                        payload.update(
                            {
                                "provider_preview_media_id": None,
                                "provider_full_media_id": None,
                            }
                        )
                    _PUBLISHING_SERVICE.record_asset_upload_payload(
                        asset_id=content_id,
                        upload_payload=payload,
                    )

                except Exception as e:
                    upload_result = {
                        "success": False,
                        "error": str(e),
                    }

                    payload = _PUBLISHING_SERVICE.build_provider_status_update(
                        provider_status="failed",
                        provider_error=str(e),
                        provider_metadata={},
                    )
                    payload.update(
                        {
                            "provider_preview_media_id": None,
                            "provider_full_media_id": None,
                        }
                    )
                    _PUBLISHING_SERVICE.record_asset_upload_payload(
                        asset_id=content_id,
                        upload_payload=payload,
                    )
            else:
                upload_result = {
                    "success": True,
                    "skipped": True,
                    "status": "not_requested",
                    "reason": "fanvue_upload_disabled",
                }

            db_save_result = {
                "success": True,
                "saved": True,
                "content_id": content_id,
                "product_draft_result": product_draft_result,
                "fanvue_upload_result": upload_result,
                "db_payload": db_payload,
            }

        return {
            "success": True,
            "upload_intent": "teaser_image",
            "image_path": str(image_path),
            "file_name": image_path.name,
            "nudenet": [],
            "gpt_vision_raw": gpt_result_raw,
            "final_classification_result": final_result,
            "final_classification": "TEASE",
            "distribution_rules": distribution_rules,
            "db_save_result": db_save_result,
        }

    # =========================================
    # 🟣 WALL IMAGE — Vision only, auto-approved
    # =========================================
    if upload_intent == "wall_image":
        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return {
                "success": False,
                "error": f"Unsupported image file type: {image_path.suffix}",
            }

        gpt_result_raw = run_gpt_vision(image_path, upload_intent)

        final_result = {
            "final_classification": "TEASE",
            "rule_applied": "forced_wall_image",
            "raw_gpt_classification": gpt_result_raw.get("classification"),
        }

        distribution_rules = get_distribution_rules("TEASE")

        db_save_result = {
            "saved": False,
            "reason": "save_to_db_false",
        }

        if save_to_db:
            db_payload = build_db_payload(
                image_path=image_path,
                nudenet_result=[],
                gpt_result_raw=gpt_result_raw,
                final_result=final_result,
                is_test=is_test,
            )

            db_payload.update({
                "upload_intent": "wall_image",
                "requires_nudenet": False,
                "requires_blur": False,
                "requires_vision": True,
                "status": "approved",
                "ready_for_rotation": True,
                "content_type": "wall",
            })
            add_context_to_payload(
                db_payload,
                image_path=image_path,
                upload_intent="wall_image",
                gpt_result_raw=gpt_result_raw,
                nudenet_result=[],
                final_result=final_result,
                fanvue_account_id=fanvue_account_id,
                creator_profile_id=creator_profile_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=mass_ppv_price,
                fanvue_upload_enabled=fanvue_upload_enabled,
                original_filename=original_filename,
            )

            content_id = insert_content_item(db_payload)
            product_draft_result = (
                create_ai_product_draft_for_content(
                    content_id,
                    creator_profile_id,
                )
                if create_product_draft
                else {
                    "success": True,
                    "created": False,
                    "reason": "product_draft_deferred",
                }
            )

            db_save_result = {
                "success": True,
                "saved": True,
                "content_id": content_id,
                "product_draft_result": product_draft_result,
                "db_payload": db_payload,
            }

        return {
            "success": True,
            "upload_intent": "wall_image",
            "image_path": str(image_path),
            "file_name": image_path.name,
            "nudenet": [],
            "gpt_vision_raw": gpt_result_raw,
            "final_classification_result": final_result,
            "final_classification": "TEASE",
            "distribution_rules": distribution_rules,
            "db_save_result": db_save_result,
            "generated_captions": [],
        }

    # =========================================
    # 🔵 TEASER VIDEO — forced TEASE, auto-approved
    # Frame Vision/tagging comes later
    # =========================================
    if upload_intent == "teaser_video":
        final_classification = "TEASE"
        distribution_rules = get_distribution_rules(final_classification)

        db_save_result = {
            "saved": False,
            "reason": "save_to_db_false",
        }

        if save_to_db:
            db_payload = {
                "file_path": str(image_path),
                "file_name": image_path.name,
                "classification": final_classification,
                "confidence": 1.0,
                "detected_themes": json.dumps([]),
                "suggested_tags": json.dumps([]),
                "nudity_labels": json.dumps([]),
                "nudity_level": "none",
                "sexual_intensity": "low",
                "is_explicit": False,
                "is_test": is_test,
                "upload_intent": "teaser_video",
                "requires_nudenet": False,
                "requires_blur": False,
                "requires_vision": True,
                "status": "approved",
                "ready_for_rotation": True,
                "content_type": "teaser",
            }
            add_context_to_payload(
                db_payload,
                image_path=image_path,
                upload_intent="teaser_video",
                gpt_result_raw={},
                nudenet_result=[],
                final_result={
                    "final_classification": final_classification,
                    "rule_applied": "forced_teaser_video",
                },
                fanvue_account_id=fanvue_account_id,
                creator_profile_id=creator_profile_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=mass_ppv_price,
                fanvue_upload_enabled=fanvue_upload_enabled,
                original_filename=original_filename,
            )

            content_id = insert_content_item(db_payload)
            product_draft_result = (
                create_ai_product_draft_for_content(
                    content_id,
                    creator_profile_id,
                )
                if create_product_draft
                else {
                    "success": True,
                    "created": False,
                    "reason": "product_draft_deferred",
                }
            )

            db_save_result = {
                "success": True,
                "saved": True,
                "content_id": content_id,
                "product_draft_result": product_draft_result,
                "db_payload": db_payload,
            }

        return {
            "success": True,
            "upload_intent": "teaser_video",
            "image_path": str(image_path),
            "file_name": image_path.name,
            "nudenet": [],
            "gpt_vision_raw": {},
            "final_classification_result": {
                "final_classification": final_classification,
                "rule_applied": "forced_teaser_video",
            },
            "final_classification": final_classification,
            "distribution_rules": distribution_rules,
            "db_save_result": db_save_result,
        }

    # =========================================
    # 🟣 WALL VIDEO — forced TEASE, auto-approved
    # =========================================
    if upload_intent == "wall_video":
        final_classification = "TEASE"
        distribution_rules = get_distribution_rules(final_classification)

        db_save_result = {
            "saved": False,
            "reason": "save_to_db_false",
        }

        if save_to_db:
            db_payload = {
                "file_path": str(image_path),
                "file_name": image_path.name,
                "classification": final_classification,
                "confidence": 1.0,
                "detected_themes": json.dumps([]),
                "suggested_tags": json.dumps([]),
                "nudity_labels": json.dumps([]),
                "nudity_level": "none",
                "sexual_intensity": "low",
                "is_explicit": False,
                "is_test": is_test,
                "upload_intent": "wall_video",
                "requires_nudenet": False,
                "requires_blur": False,
                "requires_vision": True,
                "status": "approved",
                "ready_for_rotation": True,
                "content_type": "wall",
            }
            add_context_to_payload(
                db_payload,
                image_path=image_path,
                upload_intent="wall_video",
                gpt_result_raw={},
                nudenet_result=[],
                final_result={
                    "final_classification": final_classification,
                    "rule_applied": "forced_wall_video",
                },
                fanvue_account_id=fanvue_account_id,
                creator_profile_id=creator_profile_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=mass_ppv_price,
                fanvue_upload_enabled=fanvue_upload_enabled,
                original_filename=original_filename,
            )

            content_id = insert_content_item(db_payload)
            product_draft_result = (
                create_ai_product_draft_for_content(
                    content_id,
                    creator_profile_id,
                )
                if create_product_draft
                else {
                    "success": True,
                    "created": False,
                    "reason": "product_draft_deferred",
                }
            )

            db_save_result = {
                "success": True,
                "saved": True,
                "content_id": content_id,
                "product_draft_result": product_draft_result,
                "db_payload": db_payload,
            }

        return {
            "success": True,
            "upload_intent": "wall_video",
            "image_path": str(image_path),
            "file_name": image_path.name,
            "nudenet": [],
            "gpt_vision_raw": {},
            "final_classification_result": {
                "final_classification": final_classification,
                "rule_applied": "forced_wall_video",
            },
            "final_classification": final_classification,
            "distribution_rules": distribution_rules,
            "db_save_result": db_save_result,
        }

    # =========================================
    # 🔴 PPV VIDEO — forced PREMIUM, manual approval
    # =========================================
    if upload_intent == "ppv_video":
        final_classification = "PREMIUM"
        distribution_rules = get_distribution_rules(final_classification)

        db_save_result = {
            "saved": False,
            "reason": "save_to_db_false",
        }

        if save_to_db:
            db_payload = {
                "file_path": str(image_path),
                "file_name": image_path.name,
                "classification": final_classification,
                "confidence": 1.0,
                "detected_themes": json.dumps([]),
                "suggested_tags": json.dumps([]),
                "nudity_labels": json.dumps([]),
                "nudity_level": "unknown",
                "sexual_intensity": "high",
                "is_explicit": True,
                "is_test": is_test,
                "upload_intent": "ppv_video",
                "requires_nudenet": False,
                "requires_blur": False,
                "requires_vision": True,
                "status": "approved",
                "ready_for_rotation": True,
                "content_type": "ppv",
            }
            add_context_to_payload(
                db_payload,
                image_path=image_path,
                upload_intent="ppv_video",
                gpt_result_raw={},
                nudenet_result=[],
                final_result={
                    "final_classification": final_classification,
                    "rule_applied": "forced_ppv_video_premium",
                },
                fanvue_account_id=fanvue_account_id,
                creator_profile_id=creator_profile_id,
                content_tier=content_tier,
                distribution_type=distribution_type,
                mass_ppv_price=mass_ppv_price,
                fanvue_upload_enabled=fanvue_upload_enabled,
                original_filename=original_filename,
            )

            content_id = insert_content_item(db_payload)
            product_draft_result = (
                create_ai_product_draft_for_content(
                    content_id,
                    creator_profile_id,
                )
                if create_product_draft
                else {
                    "success": True,
                    "created": False,
                    "reason": "product_draft_deferred",
                }
            )

            db_save_result = {
                "success": True,
                "saved": True,
                "content_id": content_id,
                "product_draft_result": product_draft_result,
                "db_payload": db_payload,
            }

        return {
            "success": True,
            "upload_intent": "ppv_video",
            "image_path": str(image_path),
            "file_name": image_path.name,
            "nudenet": [],
            "gpt_vision_raw": {},
            "final_classification_result": {
                "final_classification": final_classification,
                "rule_applied": "forced_ppv_video_premium",
            },
            "final_classification": final_classification,
            "distribution_rules": distribution_rules,
            "db_save_result": db_save_result,
        }

    # =========================================
    # 🟠 PPV IMAGE — NudeNet + Vision + Rules, manual approval
    # =========================================
    if upload_intent != "ppv_image":
        return {
            "success": False,
            "error": f"Unsupported upload_intent: {upload_intent}",
        }

    if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {
            "success": False,
            "error": f"Unsupported image file type: {image_path.suffix}",
        }

    nudenet_result = run_nudenet(image_path)
    gpt_result_raw = run_gpt_vision(image_path, upload_intent)
    final_result = apply_tier_rules(gpt_result_raw, nudenet_result)

    final_classification = final_result.get("final_classification", "EDGE_CASE")
    distribution_rules = get_distribution_rules(final_classification)

    db_save_result = {
        "saved": False,
        "reason": "save_to_db_false",
    }

    if save_to_db:
        db_payload = build_db_payload(
            image_path=image_path,
            nudenet_result=nudenet_result,
            gpt_result_raw=gpt_result_raw,
            final_result=final_result,
            is_test=is_test,
        )

        db_payload.update({
            "upload_intent": "ppv_image",
            "requires_nudenet": True,
            "requires_blur": True,
            "requires_vision": True,
            "status": "approved",
            "ready_for_rotation": True,
            "content_type": "ppv",
        })
        add_context_to_payload(
            db_payload,
            image_path=image_path,
            upload_intent="ppv_image",
            gpt_result_raw=gpt_result_raw,
            nudenet_result=nudenet_result,
            final_result=final_result,
            fanvue_account_id=fanvue_account_id,
            creator_profile_id=creator_profile_id,
            content_tier=content_tier,
            distribution_type=distribution_type,
            mass_ppv_price=mass_ppv_price,
            fanvue_upload_enabled=fanvue_upload_enabled,
            original_filename=original_filename,
        )

        content_id = insert_content_item(db_payload)

        db_save_result = {
            "success": True,
            "saved": True,
            "content_id": content_id,
            "db_payload": db_payload,
        }

    return {
        "success": True,
        "upload_intent": "ppv_image",
        "image_path": str(image_path),
        "file_name": image_path.name,
        "nudenet": nudenet_result,
        "gpt_vision_raw": gpt_result_raw,
        "final_classification_result": final_result,
        "final_classification": final_classification,
        "distribution_rules": distribution_rules,
        "db_save_result": db_save_result,
    }

