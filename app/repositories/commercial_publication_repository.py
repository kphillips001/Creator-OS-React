"""Persistence for provider-neutral Commercial Publication records."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID, uuid4
from datetime import timedelta, timezone

from app.database import get_db_connection
from app.models.commercial_publication import (
    CommercialPublication,
    CommercialPublicationProvider,
    CommercialPublicationStatus,
    ProviderResourceStatus,
)


class CommercialPublicationRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def create(
        self, *, commercial_offering_id: UUID,
        provider: CommercialPublicationProvider,
        status: CommercialPublicationStatus,
        publication_metadata: Mapping | None = None,
    ) -> CommercialPublication:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.commercial_publications
                       (publication_id,commercial_offering_id,provider,status,publication_metadata)
                       VALUES (%s,%s,%s,%s,%s::jsonb) RETURNING *""",
                    (uuid4(), commercial_offering_id, provider.value, status.value,
                     json.dumps(dict(publication_metadata or {}))),
                )
                row = cursor.fetchone()
        return self._from_row(row)

    def get(
        self, publication_id: UUID, *, creator_profile_id: int,
    ) -> CommercialPublication | None:
        return self._one(
            """SELECT publication.* FROM public.commercial_publications publication
               JOIN public.commercial_offerings offering
                 ON offering.offering_id=publication.commercial_offering_id
               WHERE publication.publication_id=%s AND offering.creator_profile_id=%s""",
            (publication_id, creator_profile_id),
        )

    def get_by_offering_provider(
        self, commercial_offering_id: UUID,
        provider: CommercialPublicationProvider,
    ) -> CommercialPublication | None:
        return self._one(
            """SELECT * FROM public.commercial_publications
               WHERE commercial_offering_id=%s AND provider=%s""",
            (commercial_offering_id, provider.value),
        )

    def list(
        self, *, creator_profile_id: int,
        commercial_offering_id: UUID | None = None,
    ) -> tuple[CommercialPublication, ...]:
        filters = ["offering.creator_profile_id=%s"]
        params: list = [creator_profile_id]
        if commercial_offering_id:
            filters.append("publication.commercial_offering_id=%s")
            params.append(commercial_offering_id)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT publication.* FROM public.commercial_publications publication
                        JOIN public.commercial_offerings offering
                          ON offering.offering_id=publication.commercial_offering_id
                        WHERE {' AND '.join(filters)}
                        ORDER BY publication.created_at DESC, publication.publication_id DESC""",
                    tuple(params),
                )
                rows = cursor.fetchall()
        return tuple(self._from_row(row) for row in rows)

    def update_status(
        self, publication_id: UUID, *, creator_profile_id: int,
        status: CommercialPublicationStatus, external_product_id: str | None,
        published_at: datetime | None, last_error: str | None,
        retry_count: int,
    ) -> CommercialPublication | None:
        return self._one(
            """UPDATE public.commercial_publications publication
               SET status=%s,external_product_id=%s,published_at=%s,last_error=%s,
                   retry_count=%s,updated_at=now()
               FROM public.commercial_offerings offering
               WHERE publication.publication_id=%s
                 AND offering.offering_id=publication.commercial_offering_id
                 AND offering.creator_profile_id=%s
               RETURNING publication.*""",
            (status.value, external_product_id, published_at, last_error,
             retry_count, publication_id, creator_profile_id),
        )

    def claim_execution(self, publication_id: UUID, *, creator_profile_id: int,
                        lease_seconds: int = 3600):
        token = uuid4()
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.commercial_publications publication
                       SET execution_claim_token=%s,
                           execution_lease_expires_at=now()+(%s * interval '1 second'),
                           updated_at=now()
                       FROM public.commercial_offerings offering
                       WHERE publication.publication_id=%s
                         AND offering.offering_id=publication.commercial_offering_id
                         AND offering.creator_profile_id=%s
                         AND (publication.execution_lease_expires_at IS NULL
                              OR publication.execution_lease_expires_at < now())
                       RETURNING publication.*""",
                    (token, lease_seconds, publication_id, creator_profile_id),
                )
                row = cursor.fetchone()
        return token if row else None

    def release_execution(self, publication_id: UUID, claim_token: UUID):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.commercial_publications
                       SET execution_claim_token=NULL,execution_lease_expires_at=NULL,updated_at=now()
                       WHERE publication_id=%s AND execution_claim_token=%s""",
                    (publication_id, claim_token),
                )

    def update_metadata(self, publication_id: UUID, *, creator_profile_id: int, metadata):
        return self._one(
            """UPDATE public.commercial_publications publication
               SET publication_metadata=%s::jsonb,updated_at=now()
               FROM public.commercial_offerings offering
               WHERE publication.publication_id=%s
                 AND offering.offering_id=publication.commercial_offering_id
                 AND offering.creator_profile_id=%s RETURNING publication.*""",
            (json.dumps(dict(metadata)), publication_id, creator_profile_id),
        )

    def finalize_live(self, publication_id: UUID, *, creator_profile_id: int,
                      external_product_id: str, metadata, connection=None):
        return self._one(
            """UPDATE public.commercial_publications publication
               SET status='LIVE',external_product_id=%s,publication_metadata=%s::jsonb,
                   published_at=now(),last_error=NULL,updated_at=now(),
                   provider_resource_status='PRESENT',last_reconciled_at=now(),
                   reconciliation_result='PROVIDER_RESOURCE_CONFIRMED'
               FROM public.commercial_offerings offering
               WHERE publication.publication_id=%s
                 AND publication.status='PUBLISHING'
                 AND offering.offering_id=publication.commercial_offering_id
                 AND offering.creator_profile_id=%s RETURNING publication.*""",
            (external_product_id, json.dumps(dict(metadata)), publication_id, creator_profile_id),
            connection=connection,
        )

    def record_reconciliation(
        self, publication_id: UUID, *, creator_profile_id: int,
        resource_status: ProviderResourceStatus, result: str,
        archive_live: bool = False,
    ):
        return self._one(
            """UPDATE public.commercial_publications publication
               SET provider_resource_status=%s,last_reconciled_at=now(),
                   reconciliation_result=%s,
                   status=CASE WHEN %s AND publication.status='LIVE'
                               THEN 'ARCHIVED' ELSE publication.status END,
                   updated_at=now()
               FROM public.commercial_offerings offering
               WHERE publication.publication_id=%s
                 AND offering.offering_id=publication.commercial_offering_id
                 AND offering.creator_profile_id=%s
               RETURNING publication.*""",
            (resource_status.value, result, archive_live,
             publication_id, creator_profile_id),
        )

    def list_resume_candidates(self, limit: int = 10):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT publication.*,offering.creator_profile_id
                       FROM public.commercial_publications publication
                       JOIN public.commercial_offerings offering
                         ON offering.offering_id=publication.commercial_offering_id
                       WHERE publication.status='PUBLISHING'
                         AND (publication.execution_lease_expires_at IS NULL
                              OR publication.execution_lease_expires_at<now())
                       ORDER BY publication.updated_at LIMIT %s""",
                    (limit,),
                )
                rows = cursor.fetchall()
        return tuple((self._from_row(row), int(row["creator_profile_id"])) for row in rows)

    def _one(self, sql, params, connection=None) -> CommercialPublication | None:
        if connection is not None:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
        else:
            with self._connection_factory() as managed:
                with managed.cursor() as cursor:
                    cursor.execute(sql, params)
                    row = cursor.fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row) -> CommercialPublication:
        metadata = row.get("publication_metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return CommercialPublication(
            publication_id=UUID(str(row["publication_id"])),
            commercial_offering_id=UUID(str(row["commercial_offering_id"])),
            provider=CommercialPublicationProvider(row["provider"]),
            status=CommercialPublicationStatus(row["status"]),
            external_product_id=row.get("external_product_id"),
            published_at=CommercialPublicationRepository._datetime(row.get("published_at")),
            created_at=CommercialPublicationRepository._datetime(row["created_at"]),
            updated_at=CommercialPublicationRepository._datetime(row["updated_at"]),
            last_error=row.get("last_error"), retry_count=int(row.get("retry_count") or 0),
            publication_metadata=dict(metadata),
            provider_resource_status=ProviderResourceStatus(
                row.get("provider_resource_status") or "UNVERIFIED"
            ),
            last_reconciled_at=CommercialPublicationRepository._datetime(
                row.get("last_reconciled_at")
            ),
            reconciliation_result=row.get("reconciliation_result"),
        )

    @staticmethod
    def _datetime(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
