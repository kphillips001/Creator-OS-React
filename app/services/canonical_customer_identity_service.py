"""Operator-controlled exact identity linking; never performs fuzzy matching."""
from app.repositories.canonical_customer_identity_repository import CanonicalCustomerIdentityRepository


class CanonicalCustomerIdentityService:
    def __init__(self, repository=None): self.repository=repository or CanonicalCustomerIdentityRepository()

    def reconciliation_preview(self, *, creator_profile_id):
        return [{"commerceProfileId":str(row["customer_commerce_profile_id"]),
                 "fanvueBuyerIdMasked":self._mask(row["external_fanvue_user_uuid"]),
                 "handle":row.get("handle"),"purchaseCount":int(row.get("purchase_count") or 0)}
                for row in self.repository.missing_commerce_customers(creator_profile_id=creator_profile_id)]

    def materialize(self, *, commerce_profile_id, dry_run=True):
        return self.repository.materialize(profile_id=commerce_profile_id,dry_run=dry_run)

    def metadata_enrichment_preview(self, **values):
        result=self.repository.metadata_enrichment_preview(**values)
        return {**result,'customer':{'id':result['customer']['id'],
            'fanvueUserUuidMasked':self._mask(result['customer']['fanvue_user_uuid']),
            'username':result['customer'].get('username'),'displayName':result['customer'].get('display_name'),
            'source':result['customer'].get('source')}}

    def apply_metadata_enrichment(self, **values):
        return self.repository.apply_metadata_enrichment(**values)

    def observed_x_identities(self, *, creator_profile_id):
        return self.repository.observed_external(creator_profile_id=creator_profile_id,platform="X")

    def preview_x_link(self, **values):
        external=str(values.get("external_numeric_id") or "").strip()
        if not external.isdigit(): raise ValueError("A stable numeric X identity is required")
        observation=self.repository.get_observed_external(
            creator_profile_id=values["creator_profile_id"],platform="X",
            external_numeric_id=external)
        if not observation: raise LookupError("Observed stable X identity was not found")
        return {"status":"READY_FOR_EXPLICIT_VERIFICATION","platform":"X",
                "externalNumericIdMasked":self._mask(external),
                "localFanvueUserId":int(values["local_fanvue_user_id"]),
                "observedUsername":observation.get("observed_username"),"mutationPerformed":False}

    def verify_x_link(self, *, evidence_reason, **values):
        reason=str(evidence_reason or "").strip()
        if len(reason)<10 or len(reason)>500: raise ValueError("Verification evidence must be between 10 and 500 characters")
        return self.repository.verify_external(platform="X",evidence={"operator_reason":reason},
            operator_source="CREATOR_OS_OPERATIONS",**values)

    def deactivate(self, *, link_id, reason):
        reason=str(reason or "").strip()
        if len(reason)<5: raise ValueError("Deactivation reason is required")
        return self.repository.deactivate(link_id=link_id,reason=reason,operator_source="CREATOR_OS_OPERATIONS")

    @staticmethod
    def _mask(value):
        text=str(value); return text if len(text)<=8 else f"{text[:4]}...{text[-4:]}"
