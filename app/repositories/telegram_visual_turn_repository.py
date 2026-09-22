"""Durable, bounded authority for Telegram media-turn continuity."""
from __future__ import annotations

import json
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from app.database import get_db_connection


class TelegramVisualTurnRepository:
    SCHEMA_VERSION = "telegram_visual_turn_v1"

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def establish(self, *, media_operation, member_inbound_ids=(),
                  member_message_ids=(), member_roles=(), burst_id=None,
                  authoritative_operation_id=None):
        operation_id = media_operation["operation_id"]
        turn_id = uuid5(NAMESPACE_URL, f"telegram-media-turn:{operation_id}")
        watermark = max(
            [int(x) for x in member_message_ids]
            or [int(media_operation.get("canonical_message_id") or 0)]
        )
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""INSERT INTO telegram_inbound_media_turns(
              media_turn_id,creator_profile_id,fanvue_account_id,telegram_chat_id,
              telegram_user_id,media_operation_id,conversation_burst_id,
              authoritative_response_operation_id,grouped_id,member_inbound_ids,
              member_telegram_message_ids,member_roles,newest_message_freshness_watermark,state)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s::bigint[],%s::jsonb,%s,%s)
              ON CONFLICT(media_operation_id) DO UPDATE SET
                conversation_burst_id=COALESCE(EXCLUDED.conversation_burst_id,telegram_inbound_media_turns.conversation_burst_id),
                authoritative_response_operation_id=COALESCE(telegram_inbound_media_turns.authoritative_response_operation_id,EXCLUDED.authoritative_response_operation_id),
                member_inbound_ids=(SELECT ARRAY(SELECT DISTINCT unnest(telegram_inbound_media_turns.member_inbound_ids||EXCLUDED.member_inbound_ids))),
                member_telegram_message_ids=(SELECT ARRAY(SELECT DISTINCT unnest(telegram_inbound_media_turns.member_telegram_message_ids||EXCLUDED.member_telegram_message_ids) ORDER BY 1)),
                member_roles=EXCLUDED.member_roles,
                newest_message_freshness_watermark=GREATEST(telegram_inbound_media_turns.newest_message_freshness_watermark,EXCLUDED.newest_message_freshness_watermark),
                state=CASE WHEN EXCLUDED.authoritative_response_operation_id IS NOT NULL THEN 'BOUND' ELSE telegram_inbound_media_turns.state END,
                updated_at=NOW() RETURNING *""", (
                turn_id, media_operation["creator_profile_id"], media_operation["fanvue_account_id"],
                media_operation["telegram_chat_id"], media_operation["telegram_user_id"],
                operation_id, burst_id, authoritative_operation_id,
                media_operation.get("grouped_id"), list(member_inbound_ids),
                list(member_message_ids), json.dumps(list(member_roles)), watermark,
                "BOUND" if authoritative_operation_id else "OPEN",
            ))
            return q.fetchone()

    def save_summary(self, *, media_turn, observations, retention_minutes=30):
        from app.services.customer_visual_evidence_policy import CustomerVisualEvidencePolicy
        sanitized, audit = CustomerVisualEvidencePolicy.sanitize_observations(observations)
        if audit["malformed_observations_rejected"] or audit["unknown_or_prohibited_fields_discarded"]:
            raise ValueError("visual observations failed persistence policy")
        summary_id = uuid5(NAMESPACE_URL, f"telegram-visual-summary:{media_turn['media_turn_id']}")
        attachment_ids = [row["attachment_id"] for row in sanitized]
        confidence = [float(row["confidence"]) for row in sanitized
                      if isinstance(row.get("confidence"), (int, float))]
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""INSERT INTO telegram_inbound_visual_turn_summaries(
              summary_id,creator_profile_id,fanvue_account_id,telegram_chat_id,
              telegram_user_id,media_turn_id,media_operation_id,conversation_burst_id,
              source_attachment_ids,schema_version,sanitized_summary,aggregate_confidence,
              expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s::jsonb,%s,NOW()+(%s*INTERVAL '1 minute'))
              ON CONFLICT(media_turn_id) DO UPDATE SET sanitized_summary=EXCLUDED.sanitized_summary,
                aggregate_confidence=EXCLUDED.aggregate_confidence,expires_at=EXCLUDED.expires_at
              RETURNING *""", (
                summary_id, media_turn["creator_profile_id"], media_turn["fanvue_account_id"],
                media_turn["telegram_chat_id"], media_turn["telegram_user_id"],
                media_turn["media_turn_id"], media_turn["media_operation_id"],
                media_turn.get("conversation_burst_id"), attachment_ids,
                self.SCHEMA_VERSION, json.dumps(sanitized),
                sum(confidence) / len(confidence) if confidence else None,
                max(1, min(60, int(retention_minutes))),
            ))
            return q.fetchone()

    def get(self, media_turn_id):
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("SELECT * FROM telegram_inbound_media_turns WHERE media_turn_id=%s", (media_turn_id,))
            return q.fetchone()

    def bind_response_owner(self, *, media_turn_id, operation_id, visual_context):
        """Bind once before generation; all members share existing lease/budget authority."""
        from app.services.gpt_service import GPTService
        with self.connection_factory() as c, c.cursor() as q:
            q.execute('SELECT * FROM telegram_inbound_media_turns WHERE media_turn_id=%s FOR UPDATE', (media_turn_id,))
            turn = q.fetchone()
            if turn is None:
                raise ValueError('MEDIA_TURN_MISSING')
            q.execute('SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s FOR UPDATE', (operation_id,))
            op = q.fetchone()
            if (op is None or op['telegram_chat_id'] != turn['telegram_chat_id']
                    or op['inbound_sender_telegram_user_id'] != turn['telegram_user_id']
                    or str(visual_context.get('operation_id')) != str(turn['media_operation_id'])
                    or (turn['authoritative_response_operation_id'] is not None
                        and str(turn['authoritative_response_operation_id']) != str(operation_id))):
                raise ValueError('MEDIA_OWNER_CONFLICT')
            if op['state'] != 'PENDING_GENERATION' or op['send_attempt_count'] != 0:
                if str(turn['authoritative_response_operation_id']) == str(operation_id):
                    return turn  # Idempotent observation, never reopen completed/claimed work.
                raise ValueError('MEDIA_OWNER_NOT_PENDING')
            q.execute('''SELECT customer_text FROM telegram_private_inbound_messages
                WHERE inbound_id=ANY(%s::uuid[]) ORDER BY telegram_message_id''', (turn['member_inbound_ids'],))
            text = '\n'.join(r['customer_text'] for r in q.fetchall() if r['customer_text'])
            obligations = sorted(set(op['burst_obligations'] or []) | set(
                GPTService.authoritative_turn_obligations(text, visual_context=visual_context)))
            members = sorted(set(turn['member_telegram_message_ids']) | {op['inbound_telegram_message_id']})
            visual = dict(visual_context)
            visual['turn_authority'] = dict(response_operation_id=str(operation_id),
                telegram_chat_id=turn['telegram_chat_id'], telegram_user_id=turn['telegram_user_id'],
                member_message_ids=members, obligations=obligations, associated_text=text)
            q.execute('''UPDATE ordinary_chat_reply_operations SET
                burst_freshness_telegram_message_id=GREATEST(burst_freshness_telegram_message_id,%s),
                burst_obligations=%s::jsonb,
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                updated_at=NOW() WHERE operation_id=%s''',
                (max(members), json.dumps(obligations), json.dumps({'current_turn_visual_context':visual}), operation_id))
            q.execute('''UPDATE telegram_inbound_media_turns SET
                authoritative_response_operation_id=%s, conversation_burst_id=%s,
                state='BOUND',updated_at=NOW() WHERE media_turn_id=%s RETURNING *''',
                (operation_id, op['conversation_burst_id'], media_turn_id))
            return q.fetchone()

    def attach_adjacent_text(self, *, creator_profile_id, fanvue_account_id,
                             telegram_chat_id, inbound_id, telegram_message_id,
                             window_seconds=30):
        """Bind text only to the one still-open media response opportunity."""
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""UPDATE telegram_inbound_media_turns turn SET
              member_inbound_ids=(SELECT ARRAY(SELECT DISTINCT unnest(turn.member_inbound_ids||ARRAY[%s::uuid]))),
              member_telegram_message_ids=(SELECT ARRAY(SELECT DISTINCT unnest(turn.member_telegram_message_ids||ARRAY[%s::bigint]) ORDER BY 1)),
              member_roles=turn.member_roles||jsonb_build_array(jsonb_build_object(
                'inbound_id',%s::text,'telegram_message_id',%s::bigint,'role','TEXT')),
              newest_message_freshness_watermark=GREATEST(turn.newest_message_freshness_watermark,%s),
              updated_at=NOW()
              WHERE turn.media_turn_id=(SELECT candidate.media_turn_id
                FROM telegram_inbound_media_turns candidate
                WHERE candidate.creator_profile_id=%s AND candidate.fanvue_account_id=%s
                  AND candidate.telegram_chat_id=%s
                  AND (candidate.state='OPEN' AND candidate.authoritative_response_operation_id IS NULL
                    OR candidate.state='BOUND' AND EXISTS (SELECT 1 FROM ordinary_chat_reply_operations owner
                        WHERE owner.operation_id=candidate.authoritative_response_operation_id
                          AND owner.state='PENDING_GENERATION' AND owner.send_attempt_count=0))
                  AND candidate.created_at>=NOW()-(%s*INTERVAL '1 second')
                  AND candidate.newest_message_freshness_watermark<%s
                ORDER BY candidate.created_at DESC LIMIT 1 FOR UPDATE SKIP LOCKED)
              RETURNING turn.*""", (
                inbound_id, telegram_message_id, inbound_id, telegram_message_id,
                telegram_message_id, creator_profile_id, fanvue_account_id,
                telegram_chat_id, max(1, min(60, int(window_seconds))),
                telegram_message_id,
            ))
            turn = q.fetchone()
            if turn and turn['authoritative_response_operation_id']:
                q.execute('SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s FOR UPDATE',
                          (turn['authoritative_response_operation_id'],))
                owner = q.fetchone()
                if owner['state'] != 'PENDING_GENERATION' or owner['send_attempt_count']:
                    raise ValueError('MEDIA_OWNER_CHANGED_DURING_ASSOCIATION')
                q.execute("SELECT customer_text FROM telegram_private_inbound_messages WHERE inbound_id=ANY(%s::uuid[]) ORDER BY telegram_message_id", (turn['member_inbound_ids'],))
                text = '\n'.join(r['customer_text'] for r in q.fetchall() if r['customer_text'])
                from app.services.gpt_service import GPTService
                visual = dict((owner['delivery_payload'] or {}).get('current_turn_visual_context') or {})
                obligations = sorted(set(owner['burst_obligations'] or []) | set(
                    GPTService.authoritative_turn_obligations(text, visual_context=visual)))
                authority = dict(visual.get('turn_authority') or {})
                authority.update(associated_text=text, obligations=obligations,
                    member_message_ids=sorted(set(turn['member_telegram_message_ids']) | {owner['inbound_telegram_message_id']}))
                visual['turn_authority'] = authority
                q.execute("""UPDATE ordinary_chat_reply_operations SET
                    burst_freshness_telegram_message_id=GREATEST(burst_freshness_telegram_message_id,%s),
                    burst_obligations=%s::jsonb,
                    delivery_payload=delivery_payload||%s::jsonb,updated_at=NOW()
                    WHERE operation_id=%s""", (turn['newest_message_freshness_watermark'],
                    json.dumps(obligations), json.dumps({'current_turn_visual_context': visual}), owner['operation_id']))
            return turn

    def member_text(self, media_turn_id):
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""SELECT inbound.customer_text,inbound.telegram_message_id
              FROM telegram_inbound_media_turns turn
              JOIN telegram_private_inbound_messages inbound
                ON inbound.inbound_id=ANY(turn.member_inbound_ids)
              WHERE turn.media_turn_id=%s AND inbound.customer_text<>''
              ORDER BY inbound.received_at,inbound.telegram_message_id""", (media_turn_id,))
            return q.fetchall()

    def live_summaries(self, *, creator_profile_id, fanvue_account_id,
                       telegram_chat_id, limit=3):
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""SELECT summary_id,media_turn_id,conversation_burst_id,
              sanitized_summary,aggregate_confidence,created_at,expires_at,
              identity_authority,sensitive_inference_authority
              FROM telegram_inbound_visual_turn_summaries
              WHERE creator_profile_id=%s AND fanvue_account_id=%s
                AND telegram_chat_id=%s AND expires_at>NOW()
              ORDER BY created_at DESC LIMIT %s""", (
                creator_profile_id, fanvue_account_id, telegram_chat_id,
                max(1, min(3, int(limit))),
            ))
            return q.fetchall()
