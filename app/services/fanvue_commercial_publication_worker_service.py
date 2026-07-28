"""Resumes durable Fanvue Commercial Publications left in PUBLISHING."""
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.services.fanvue_media_link_publication_executor import FanvueMediaLinkPublicationExecutor

class FanvueCommercialPublicationWorkerService:
    def __init__(self, repository=None, executor=None):
        self.repository = repository or CommercialPublicationRepository()
        self.executor = executor or FanvueMediaLinkPublicationExecutor(publications=self.repository)

    def process_one(self):
        candidates = self.repository.list_resume_candidates(limit=1)
        if not candidates:
            return {"processed": False}
        publication, creator_profile_id = candidates[0]
        account_id = publication.publication_metadata.get("fanvue_account_id")
        if not account_id:
            return {"processed": False, "reason": "missing_fanvue_account_id"}
        self.executor.execute(
            publication.publication_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=int(account_id))
        return {"processed": True, "publication_id": str(publication.publication_id)}
