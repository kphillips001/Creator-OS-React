"""Non-production certification for visual-turn ordering and provider authority."""
import inspect

import pytest

from app.services.customer_media_multimodal_decision_engine import (
    CustomerMediaMultimodalDecisionEngine,
)
from app.services.telegram_visual_turn_service import TelegramVisualTurnService
from app.services.telegram_turn_reservation_service import TelegramTurnReservationService


class TurnRepository:
    def __init__(self):
        self.turn = None
        self.text = []

    def establish(self, **values):
        self.turn = {"media_turn_id": "turn", **values}
        return self.turn

    def attach_adjacent_text(self, **values):
        if self.turn is None:
            return None
        self.text.append(values["telegram_message_id"])
        return self.turn

    def member_text(self, _turn_id):
        return [{"customer_text": "I hope you like it"}] if self.text else []


class Inbound:
    inbound_id = "00000000-0000-0000-0000-000000000010"
    telegram_message_id = 11
    customer_text = "I hope you like it"


def media_operation():
    return {"operation_id": "media", "creator_profile_id": 2,
            "fanvue_account_id": 2, "telegram_chat_id": 3,
            "telegram_user_id": 3, "grouped_id": None}


def test_image_then_text_has_one_open_turn_and_advances_membership():
    repo = TurnRepository(); service = TelegramVisualTurnService(repository=repo)
    service.establish(media_operation=media_operation(), inbound_members=({
        "inbound_id": "00000000-0000-0000-0000-000000000009",
        "telegram_message_id": 10, "has_media": True},))
    associated = service.attach_adjacent_text(
        creator_profile_id=2, fanvue_account_id=2,
        telegram_chat_id=3, inbound=Inbound())
    assert associated["media_turn_id"] == "turn"
    assert service.associated_text("turn") == "I hope you like it"


def test_text_then_image_reserves_exactly_one_response_owner():
    class Reservations:
        def __init__(self): self.row=None
        def open_text(self, **values):
            self.row={"reservation_id":"reservation","state":"OPEN",
                      "authoritative_response_operation_id":None,
                      "newest_message_freshness_watermark":11}
            return self.row
        def bind_owner(self, reservation_id, operation_id):
            self.row.update(authoritative_response_operation_id=operation_id)
            return self.row
        def join_media(self, **_values):
            self.row.update(state="READY",newest_message_freshness_watermark=12)
            return self.row
    repo=Reservations(); service=TelegramTurnReservationService(repository=repo)
    reserved=service.reserve_text(creator_profile_id=2,fanvue_account_id=2,inbound=Inbound())
    service.bind_owner(reserved["reservation_id"],"operation-1")
    joined=service.join_media(creator_profile_id=2,fanvue_account_id=2,inbound=Inbound())
    assert joined["state"] == "READY"
    assert joined["authoritative_response_operation_id"] == "operation-1"
    assert joined["newest_message_freshness_watermark"] == 12


def test_provider_contract_is_one_call_store_false_and_no_tools():
    source = inspect.getsource(CustomerMediaMultimodalDecisionEngine._openai)
    assert "store=False" in source
    assert "tools=[]" in source
    assert source.count("responses.create") == 1
