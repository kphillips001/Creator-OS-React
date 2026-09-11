"""Read-only operational incidents from canonical commercial lifecycles."""
from app.database import get_db_connection


class CommercialOperationsRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory=connection_factory

    def incidents(self, *, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT purchase_intent_id::text AS id,'PurchaseIntent' AS source,status,
                          'Active PurchaseIntent passed its expiry without terminal reconciliation.' AS error,
                          updated_at AS timestamp,0 AS retry_count,
                          jsonb_build_object('customerId',external_fanvue_user_uuid,'offeringId',commercial_offering_id) AS related
                     FROM purchase_intents
                    WHERE fanvue_account_id=%s AND status IN ('CREATED','PRESENTED','CLICKED') AND expires_at<NOW()
                   UNION ALL
                   SELECT sales_session_id::text,'Sales Session',state,
                          'Active Sales Session has no activity within the seven-day operational window.',
                          updated_at,0,jsonb_build_object('customerId',external_fanvue_user_uuid)
                     FROM sales_sessions
                    WHERE fanvue_account_id=%s AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')
                      AND last_activity_at<NOW()-INTERVAL '7 days'
                   ORDER BY timestamp DESC""", (fanvue_account_id,fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]
