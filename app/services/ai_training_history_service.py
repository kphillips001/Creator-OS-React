"""Logical, baseline-aware projection for normal operator Training History."""
from datetime import datetime, timezone

from app.repositories.ai_training_control_repository import AiTrainingControlRepository
from app.repositories.ai_training_history_baseline_repository import AiTrainingHistoryBaselineRepository


class AiTrainingHistoryService:
    def __init__(self, training=None, baselines=None, clock=None):
        self.training = training or AiTrainingControlRepository()
        self.baselines = baselines or AiTrainingHistoryBaselineRepository()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list_visible(self, *, creator_profile_id, fanvue_account_id):
        baseline = self.baselines.get(creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
        items = [*self.training.list(creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id),
                 *self.training.list_all_customer(creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)]
        if not baseline:
            return {"baselineAt": None, "items": items}
        retained = {str(value) for value in baseline["retained_instruction_ids"]}
        visible = [item for item in items if str(item.instruction_id) in retained or item.created_at > baseline["baseline_at"]]
        visible.sort(key=lambda item: (item.updated_at, str(item.instruction_id)), reverse=True)
        return {"baselineAt": baseline["baseline_at"], "items": visible}

    def establish_current(self, *, creator_profile_id, fanvue_account_id, retained_instruction_ids):
        return self.baselines.establish(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,baseline_at=self.clock(),
            retained_instruction_ids=retained_instruction_ids)
