from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.rows import dict_row

from app.repositories.x_thread_cta_delivery_repository import (
    XThreadCtaDeliveryRepository,
)
from app.testing.postgres_safety import (
    require_isolated_test_database_url,
    verify_isolated_test_connection,
)


def test_x_thread_cta_delivery_persistence_contract():
    production = os.environ.get("PRODUCTION_DATABASE_URL")
    url = require_isolated_test_database_url(
        os.environ.get("CERTIFICATION_DATABASE_URL"), production,
    )

    @contextmanager
    def factory():
        with connect(url, row_factory=dict_row) as connection:
            verify_isolated_test_connection(connection, url, production)
            yield connection

    repository = XThreadCtaDeliveryRepository(connection_factory=factory)

    def attribution(operation: str) -> str:
        attribution_id = str(uuid4())
        with factory() as connection:
            connection.execute(
                "INSERT INTO public.x_link_attributions "
                "(x_link_attribution_id,attribution_token,creator_profile_id,"
                "fanvue_account_id,publish_operation_id,social_queue_item_id,"
                "generation_image_id,primary_x_post_id,x_account_name,"
                "primary_caption,primary_published_at) "
                "VALUES (%s,%s,1,2,%s,%s,%s,%s,'AvaBlackthorne','caption',NOW())",
                (attribution_id, f"token-{operation}", operation,
                 f"queue-{operation}", f"image-{operation}", f"post-{operation}"),
            )
        return attribution_id

    direct_attr = attribution("direct")
    direct = repository.claim_once(
        creator_profile_id=1, fanvue_account_id=2,
        publish_operation_id="direct", x_account_name="AvaBlackthorne",
        primary_x_post_id="post-direct", x_link_attribution_id=direct_attr,
        timing="ASAP", cta_text="Chat", cta_url="https://example.test/direct",
    )
    assert direct["_claim_acquired"] is True
    replay = repository.claim_once(
        creator_profile_id=1, fanvue_account_id=2,
        publish_operation_id="direct", x_account_name="AvaBlackthorne",
        primary_x_post_id="post-direct", x_link_attribution_id=direct_attr,
        timing="ASAP", cta_text="Chat", cta_url="https://example.test/direct",
    )
    assert replay["delivery_id"] == direct["delivery_id"]
    assert replay["_claim_acquired"] is False
    posted = repository.mark_posted(
        str(direct["delivery_id"]), reply_id="reply-direct", output_url="https://x.test/reply-direct",
    )
    assert posted["state"] == "POSTED"
    assert posted["sent_at"] is not None

    delayed_attr = attribution("delayed")
    delayed = repository.claim_once(
        creator_profile_id=1, fanvue_account_id=2,
        publish_operation_id="delayed", x_account_name="AvaBlackthorne",
        primary_x_post_id="post-delayed", x_link_attribution_id=delayed_attr,
        timing="DELAY_30_60", cta_text="Join", cta_url="https://example.test/delayed",
    )
    uncertain = repository.mark_uncertain(
        str(delayed["delivery_id"]), "provider result was not confirmed"
    )
    assert uncertain["state"] == "SEND_UNCERTAIN"
    assert uncertain["failure_reason"] == "provider result was not confirmed"
    with pytest.raises(RuntimeError):
        repository.mark_posted(
            str(delayed["delivery_id"]), reply_id="late-reply", output_url=None,
        )

    conflicting_attr = attribution("conflicting-parent")
    with pytest.raises(UniqueViolation):
        repository.claim_once(
            creator_profile_id=1, fanvue_account_id=2,
            publish_operation_id="conflicting-parent", x_account_name="AvaBlackthorne",
            primary_x_post_id="post-direct", x_link_attribution_id=conflicting_attr,
            timing="ASAP", cta_text="Chat", cta_url="https://example.test/conflict",
        )

    with pytest.raises(ForeignKeyViolation):
        repository.claim_once(
            creator_profile_id=1, fanvue_account_id=2,
            publish_operation_id="missing-attribution", x_account_name="AvaBlackthorne",
            primary_x_post_id="post-missing", x_link_attribution_id=str(uuid4()),
            timing="ASAP", cta_text="Chat", cta_url="https://example.test/missing",
        )
