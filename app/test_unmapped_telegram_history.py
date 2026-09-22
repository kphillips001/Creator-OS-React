from datetime import datetime, timedelta, timezone

from app.services.unmapped_telegram_history_service import UnmappedTelegramHistoryService


BASE = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)


def event(index, text, *, role="assistant", origin="AI", message_id=None,
          event_id=None, seconds=None):
    return {
        "event_id":event_id or f"event:{index}",
        "occurred_at":BASE+timedelta(seconds=index if seconds is None else seconds),
        "telegram_chat_id":99,
        "telegram_message_id":index if message_id is None else message_id,
        "role":role,"text":text,"origin":origin,
    }


class Source:
    def __init__(self, events): self.events=list(events);self.calls=[]
    def recent_confirmed_events(self, **scope):
        self.calls.append(scope)
        return self.events[-scope["limit"]:]


def history(ordinary=(), manual=(), limit=10, **scope):
    service=UnmappedTelegramHistoryService(
        ordinary_source=Source(ordinary),manual_source=Source(manual),final_limit=limit)
    return service.recent_history(creator_profile_id=2,fanvue_account_id=2,
        telegram_user_id=7,telegram_chat_id=99,**scope)


def contents(values): return [item["content"] for item in values]


def test_ordinary_only_is_unchanged_and_roles_are_preserved():
    assert history([event(1,"B",role="user",origin="CUSTOMER"),event(2,"A")]) == [
        {"role":"user","content":"B","origin":"CUSTOMER"},
        {"role":"assistant","content":"A","origin":"AI"}]


def test_manual_only_is_chronological_and_assistant_role():
    result=history(manual=[event(3,"C",origin="HUMAN_OPERATOR"),
        event(1,"A",origin="HUMAN_OPERATOR")])
    assert contents(result)==["A","C"]
    assert all(item["role"]=="assistant" for item in result)


def test_mixed_history_is_globally_chronological():
    assert contents(history([event(1,"A"),event(4,"D",role="user",origin="CUSTOMER")],
        [event(2,"B",origin="HUMAN_OPERATOR"),event(3,"C",origin="HUMAN_OPERATOR")])) == ["A","B","C","D"]


def test_manual_between_ordinary_and_later_ordinary_remains_after_manual():
    assert contents(history([event(1,"A"),event(3,"C")],
        [event(2,"B",origin="HUMAN_OPERATOR")])) == ["A","B","C"]


def test_multiple_manual_messages_order_correctly():
    assert contents(history(manual=[event(4,"D",origin="HUMAN_OPERATOR"),
        event(2,"B",origin="HUMAN_OPERATOR"),event(3,"C",origin="HUMAN_OPERATOR")])) == ["B","C","D"]


def test_same_text_with_different_telegram_ids_is_preserved():
    assert contents(history(manual=[event(1,"same"),event(2,"same")])) == ["same","same"]


def test_same_telegram_event_is_deduplicated_across_sources():
    assert contents(history([event(1,"same",message_id=44)],
        [event(2,"duplicate",message_id=44,origin="HUMAN_OPERATOR")])) == ["same"]


def test_final_limit_applies_after_merge_sort_and_dedup():
    assert contents(history([event(1,"A"),event(3,"C"),event(5,"E")],
        [event(2,"B"),event(4,"D"),event(6,"F")],limit=3)) == ["D","E","F"]


def test_old_events_fall_outside_final_window():
    assert contents(history([event(i,str(i)) for i in range(1,8)],limit=4)) == ["4","5","6","7"]


def test_current_inbound_exclusion_is_forwarded_only_to_ordinary_source():
    ordinary=Source([]);manual=Source([])
    service=UnmappedTelegramHistoryService(ordinary_source=ordinary,manual_source=manual)
    service.recent_history(creator_profile_id=2,fanvue_account_id=2,
        telegram_user_id=7,telegram_chat_id=99,exclude_inbound_message_id=123)
    assert ordinary.calls[0]["exclude_inbound_message_id"]==123
    assert "exclude_inbound_message_id" not in manual.calls[0]


def test_johnny_takeover_continuity():
    result=history([event(1,"😘")],
        [event(2,"Still waiting on those coffees 😘",origin="HUMAN_OPERATOR")])
    assert result[-1]=={"role":"assistant","content":"Still waiting on those coffees 😘","origin":"HUMAN_OPERATOR"}


def test_complex_interleaving_abcdef():
    ordinary=[event(1,"A"),event(2,"B",role="user",origin="CUSTOMER"),
        event(4,"D",role="user",origin="CUSTOMER"),event(5,"E"),
        event(6,"F",role="user",origin="CUSTOMER")]
    assert contents(history(ordinary,[event(3,"C",origin="HUMAN_OPERATOR")])) == list("ABCDEF")


def test_equal_timestamp_tie_break_is_stable():
    first=event(2,"two",seconds=1);second=event(1,"one",seconds=1)
    assert contents(history([first],[second])) == ["one","two"]
