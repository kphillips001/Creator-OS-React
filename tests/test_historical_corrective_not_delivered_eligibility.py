from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.historical_corrective_eligibility_service import (
    HistoricalCorrectiveEligibilityService as Service,
)
from app.services.recovery_execution_constraint_service import (
    RecoveryExecutionConstraintService,
)

NOW=datetime(2026,9,18,12,44,tzinfo=timezone.utc)


def operation(**changes):
    value=dict(operation_id="1d99dda0-515b-4073-8e9e-3b7e5b05fa75",
      operation_kind="PRIMARY",state=SimpleNamespace(value="SEND_UNCERTAIN"),
      telegram_account_scope="AVA_TELETHON_PRIVATE",telegram_chat_id=7489120428,
      inbound_telegram_message_id=6665,inbound_received_at=NOW,
      outbound_telegram_message_id=None,sent_confirmed_at=None,send_attempt_count=1,
      last_error="legacy_sendPhoto_acceptance_unknown",delivery_payload={},
      causal_operation_id=None,recovery_parent_operation_id=None,
      recovery_resolution_plan_id=None)
    value.update(changes);return SimpleNamespace(**value)


def resolution(**changes):
    value={"resolution_id":"41f7dfb0-84e8-4ec8-b090-ce7c28f68142",
      "outcome":"NOT_DELIVERED","provenance":"OPERATOR_ATTESTED",
      "provider_acceptance_evidence":False,"provider_readback_evidence":True,
      "evidence":{"classification":"CONFIRMED_NOT_DELIVERED","complete":True,
                  "matchingCandidateCount":0}}
    value.update(changes);return value


class Cursor:
    def __init__(self,repo): self.repo=repo;self.rows=[]
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def execute(self,sql,_params=()):
        if "FROM ordinary_reply_generation_attempts" in sql:
            self.rows=[{"present":1}] if self.repo.durable_candidate else []
        elif "FROM operator_delivery_resolutions" in sql: self.rows=[self.repo.resolution] if self.repo.resolution else []
        elif "FROM conversation_resolution_plans" in sql:
            self.rows=([{"parameters":self.repo.plan_parameters}]
                       if self.repo.plan_parameters is not None else [])
        elif "SELECT 1 WHERE" in sql: self.rows=[{"?column?":1}] if self.repo.stale else []
        elif "FROM telegram_private_inbound_messages" in sql:
            self.rows=[{"present":1}] if self.repo.inbound_exists else []
        elif "FROM telegram_relationship_controls" in sql: self.rows=[self.repo.control] if self.repo.control else []
        return self
    def fetchone(self): return self.rows.pop(0) if self.rows else None


class Connection:
    def __init__(self,repo): self.repo=repo
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def cursor(self): return self
    def execute(self,*args): return Cursor(self.repo).execute(*args)
    def __getattr__(self,name):
        if name in {"fetchone"}: return getattr(self._cursor,name)
        raise AttributeError(name)


class Factory:
    def __init__(self,resolution_row=None,stale=False,control=None,
                 plan_parameters=None,durable_candidate=False,inbound_exists=True):
        self.resolution=resolution_row;self.stale=stale;self.control=control
        self.plan_parameters=plan_parameters
        self.durable_candidate=durable_candidate
        self.inbound_exists=inbound_exists
    def __call__(self):
        repo=self
        class Context:
            def __enter__(self): self.cursor_object=Cursor(repo);return self
            def __exit__(self,*_): pass
            def cursor(self): return self.cursor_object
        return Context()


def evaluate(root=None,parent=None,repo=None,chat_allowed=True):
    root=root or operation();parent=parent or root
    return Service(connection_factory=repo or Factory(resolution())).evaluate(
      root=root,parent=parent,creator_profile_id=2,fanvue_account_id=2,
      telegram_user_id=7489120428,telegram_chat_id=7489120428,
      chat_allowed=chat_allowed)


def test_send_uncertain_requires_canonical_resolution():
    result=evaluate(repo=Factory(None))
    assert not result["eligible"] and result["reason"]=="CANONICAL_NOT_DELIVERED_RESOLUTION_REQUIRED"


@pytest.mark.parametrize("change",[
    {"outcome":"DELIVERED"},{"provider_readback_evidence":False},
    {"provenance":"UNTRUSTED"},{"provider_acceptance_evidence":True},
    {"evidence":{"classification":"STILL_UNCERTAIN","complete":True,"matchingCandidateCount":0}},
])
def test_non_authoritative_or_delivered_resolution_is_ineligible(change):
    assert not evaluate(repo=Factory(resolution(**change)))["eligible"]


def test_canonical_not_delivered_is_explicit_second_root_category():
    result=evaluate()
    assert result["eligible"] is True
    assert result["category"]==Service.NOT_DELIVERED
    assert result["mode"]=="FIRST_CORRECTIVE_AFTER_ATTESTED_NON_DELIVERY"


def constraint_parent(**changes):
    value=dict(operation_id="792b79a6-2a2a-421d-968c-4e8a910f333f",
      operation_kind="HISTORICAL_CORRECTIVE",state=SimpleNamespace(value="SUPPRESSED"),
      telegram_account_scope="AVA_TELETHON_PRIVATE",telegram_chat_id=7489120428,
      inbound_telegram_message_id=6665,inbound_received_at=NOW,
      outbound_telegram_message_id=None,sent_confirmed_at=None,send_attempt_count=0,
      last_error="recovery_execution_constraint_violation:OPERATOR_RECOVERY_CONVERSATION_ONLY",
      delivery_payload={},causal_operation_id="1d99dda0-515b-4073-8e9e-3b7e5b05fa75",
      recovery_parent_operation_id="1d99dda0-515b-4073-8e9e-3b7e5b05fa75",
      recovery_resolution_plan_id="95ff1050-15a3-48a1-9567-b298fa2337e6")
    value.update(changes);return SimpleNamespace(**value)


def constraint_repo(**changes):
    values={"resolution_row":resolution(),
            "plan_parameters":{"recoveryExecutionConstraint":
                               RecoveryExecutionConstraintService.authority()}}
    values.update(changes)
    return Factory(**values)


def test_repaired_constraint_failure_allows_one_bounded_follow_up():
    result=evaluate(parent=constraint_parent(),repo=constraint_repo())
    assert result["eligible"] is True
    assert result["category"]==Service.CONSTRAINT_FAILURE_FOLLOW_UP
    assert result["mode"]=="FOLLOW_UP_AFTER_REPAIRED_RECOVERY_CONSTRAINT_FAILURE"


@pytest.mark.parametrize("change",[
    {"state":SimpleNamespace(value="SEND_UNCERTAIN")},
    {"state":SimpleNamespace(value="SENT_CONFIRMED")},
    {"send_attempt_count":1},
    {"outbound_telegram_message_id":77},
    {"last_error":"quality_blocked_before_delivery:CUSTOMER_QUESTION_UNANSWERED"},
    {"recovery_parent_operation_id":"792b79a6-2a2a-421d-968c-4e8a910f333f"},
])
def test_constraint_follow_up_denies_unsafe_parent_states_and_recursive_chains(change):
    assert not evaluate(parent=constraint_parent(**change),repo=constraint_repo())["eligible"]


def test_constraint_follow_up_requires_durable_parent_plan_authority(monkeypatch):
    assert not evaluate(parent=constraint_parent(),repo=constraint_repo(
      plan_parameters={}))["eligible"]
    monkeypatch.setattr(RecoveryExecutionConstraintService,
      "supports_repaired_conversation_only_policy",classmethod(lambda cls:False))
    result=evaluate(parent=constraint_parent(),repo=constraint_repo())
    assert not result["eligible"] and result["reason"]=="CURRENT_POLICY_REPAIR_NOT_PROVEN"


def test_wrong_parent_confirmed_outbound_stale_or_denied_authority_blocks():
    assert not evaluate(parent=operation(operation_id="other"))["eligible"]
    assert not evaluate(root=operation(outbound_telegram_message_id=7))["eligible"]
    assert not evaluate(repo=Factory(resolution(),stale=True))["eligible"]
    assert not evaluate(chat_allowed=False)["eligible"]
    assert not evaluate(repo=Factory(resolution(),control={"mode":"HUMAN_OPERATOR","disposition":"ACTIVE"}))["eligible"]


def test_evaluation_does_not_mutate_original_operation():
    root=operation();before=deepcopy(vars(root));assert evaluate(root=root)["eligible"]
    assert vars(root)==before


def test_existing_quality_root_taxonomy_is_unchanged():
    root=operation(state=SimpleNamespace(value="SUPPRESSED"),send_attempt_count=0,
      last_error="quality_blocked_before_delivery:CUSTOMER_QUESTION_UNANSWERED")
    result=evaluate(root=root,parent=root,repo=Factory(None))
    assert result["eligible"] and result["category"]==Service.QUALITY


def retry_exhausted(**changes):
    values=dict(
      state=SimpleNamespace(value="TERMINAL_FAILED"),
      last_error="DECISION_ENGINE_EXCEPTION:UNKNOWN: Automatic reply could not be completed.",
      generation_attempt_count=5,max_generation_attempts=5,
      send_attempt_count=0,response_text=None,response_payload=None,
      outbound_telegram_message_id=None,sent_confirmed_at=None,
      claim_owner=None,lease_expires_at=None,
      conversation_burst_id="1d99dda0-515b-4073-8e9e-3b7e5b05fa75",
      burst_member_obligations=["ACKNOWLEDGE_SEXUAL_ENERGY"],
      delivery_payload={})
    values.update(changes)
    return operation(**values)


def test_retry_exhausted_zero_candidate_current_obligation_is_eligible_once():
    root=retry_exhausted()
    result=evaluate(root=root,parent=root,repo=Factory(None))
    assert result["eligible"] is True
    assert result["category"]==Service.RETRY_EXHAUSTED
    assert result["mode"]=="FIRST_REEVALUATION_AFTER_RETRY_EXHAUSTION"


@pytest.mark.parametrize("root,repo,reason",[
    (retry_exhausted(send_attempt_count=1),Factory(None),
     "ROOT_NOT_QUALIFYING_QUALITY_OR_NOT_DELIVERED"),
    (retry_exhausted(),Factory(None,durable_candidate=True),
     "DURABLE_GENERATED_CANDIDATE_EXISTS"),
    (retry_exhausted(burst_member_obligations=[]),Factory(None),
     "NO_SURVIVING_MEANINGFUL_OBLIGATION"),
    (retry_exhausted(),Factory(None,stale=True),"SOURCE_INBOUND_NO_LONGER_FRESH"),
])
def test_retry_exhausted_requires_complete_safe_evidence(root,repo,reason):
    result=evaluate(root=root,parent=root,repo=repo)
    assert result["eligible"] is False
    assert result["reason"]==reason


def test_retry_exhausted_existing_child_blocks_duplicate():
    root=retry_exhausted()
    child=operation(operation_id="child",operation_kind="HISTORICAL_CORRECTIVE",
                    causal_operation_id=root.operation_id)
    result=evaluate(root=root,parent=child,repo=Factory(None))
    assert result["eligible"] is False
    assert result["reason"]=="RETRY_EXHAUSTED_RECOVERY_ALREADY_EXISTS"
