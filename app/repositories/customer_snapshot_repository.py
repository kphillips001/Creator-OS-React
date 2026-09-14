"""Bounded native-authority reads for Customer Snapshot composition."""
from app.repositories.canonical_relationship_fact_repository import CanonicalRelationshipFactRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository


class CustomerSnapshotRepository:
    def __init__(self, *, identities=None, prospects=None, facts=None):
        self.identities = identities or TelegramIdentityRepository()
        self.prospects = prospects or TelegramSalesProspectRepository()
        self.facts = facts or CanonicalRelationshipFactRepository()

    def canonical_sources(self, *, creator_profile_id, fanvue_account_id,
                          customer_id):
        mapping = self.identities.get_by_local_user_id(
            fanvue_account_id, customer_id,
        )
        if mapping is not None and str(mapping.verification_status) != "VERIFIED":
            mapping = None
        prospect = None if mapping is None else self.prospects.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=mapping.telegram_user_id,
        )
        facts = self.facts.list_current(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            customer_id=customer_id,
        )
        return mapping, prospect, facts

    def prospect_sources(self, *, creator_profile_id, fanvue_account_id,
                         telegram_user_id):
        prospect = self.prospects.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        facts = self.facts.list_current(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            customer_id=None,
        )
        return prospect, facts

