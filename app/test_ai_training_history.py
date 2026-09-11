from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.ai_training_history_service import AiTrainingHistoryService


NOW=datetime(2026,9,10,tzinfo=timezone.utc)
def item(text,created,scope="GLOBAL",identifier=None,status="ENABLED",version=2):
    return SimpleNamespace(instruction_id=identifier or uuid4(),normalized_instruction=text,
        created_at=created,updated_at=created,status=status,version=version,scope=scope)
class Training:
    def __init__(self,global_items=(),customer_items=()):self.global_items=list(global_items);self.customer_items=list(customer_items)
    def list(self,**scope):return self.global_items
    def list_all_customer(self,**scope):return self.customer_items
class Baselines:
    def __init__(self,value):self.value=value
    def get(self,**scope):return self.value

def service(global_items=(),customer_items=(),retained=()):
    baseline={"baseline_at":NOW,"retained_instruction_ids":list(retained)}
    return AiTrainingHistoryService(Training(global_items,customer_items),Baselines(baseline))

def test_retained_prebaseline_visible_and_nonretained_hidden():
    keep=item("keep",NOW-timedelta(days=1));hide=item("hide",NOW-timedelta(days=2),status="ARCHIVED",version=3)
    result=service([keep,hide],retained=[keep.instruction_id]).list_visible(creator_profile_id=1,fanvue_account_id=2)
    assert [value.instruction_id for value in result["items"]]==[keep.instruction_id]

def test_postbaseline_instruction_appears_automatically():
    new=item("new",NOW+timedelta(seconds=1))
    assert service([new]).list_visible(creator_profile_id=1,fanvue_account_id=2)["items"]==[new]

def test_identity_not_text_controls_customer_isolation():
    first=item("same",NOW+timedelta(seconds=1),"CUSTOMER")
    second=item("same",NOW+timedelta(seconds=2),"CUSTOMER")
    result=service(customer_items=[first,second]).list_visible(creator_profile_id=1,fanvue_account_id=2)
    assert {value.instruction_id for value in result["items"]}=={first.instruction_id,second.instruction_id}

def test_retained_instruction_remains_one_current_object_after_lifecycle_changes():
    identifier=uuid4();current=item("edited",NOW+timedelta(days=1),identifier=identifier,status="DISABLED",version=5)
    result=service([current],retained=[identifier]).list_visible(creator_profile_id=1,fanvue_account_id=2)
    assert len(result["items"])==1 and result["items"][0].version==5 and result["items"][0].status=="DISABLED"
