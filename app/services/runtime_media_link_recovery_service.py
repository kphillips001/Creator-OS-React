"""Durable retry/reconciliation for runtime Fanvue Media Link operations."""
from app.repositories.private_chat_fingerprint_repository import PrivateChatFingerprintRepository
from app.services.fanvue_official_client import FanvueOfficialClient


class RuntimeMediaLinkRecoveryService:
    def __init__(self, repository=None, client_factory=FanvueOfficialClient):
        self.repository = repository or PrivateChatFingerprintRepository()
        self.client_factory = client_factory

    def run_once(self, *, limit=25):
        results = []
        for operation in self.repository.claim_due_operations(limit=limit):
            runtime = self.repository.operation_runtime(operation["runtime_media_link_id"])
            try:
                if runtime is None:
                    raise LookupError("Runtime Media Link disappeared.")
                client = self.client_factory(runtime["fanvue_account_id"])
                if operation["operation_type"] == "DELETE":
                    provider_uuid = runtime.get("provider_media_link_uuid")
                    if provider_uuid:
                        client.delete_media_link(provider_uuid)
                    self.repository.mark_deleted(runtime["runtime_media_link_id"])
                else:
                    metadata = runtime.get("publication_metadata") or {}
                    media = tuple((metadata.get("media_link") or {}).get("media_uuids") or ())
                    price = int(runtime["exact_price_minor"] if "exact_price_minor" in runtime
                                else runtime["expected_price_minor"])
                    matches = client.find_equivalent_media_link(media, price)
                    if len(matches) != 1:
                        raise LookupError("CREATE recovery requires exactly one provider match.")
                    link = matches[0]
                    self.repository.activate(runtime["runtime_media_link_id"],
                        provider_uuid=str(link["uuid"]), provider_url=str(link["url"]))
                self.repository.finish_operation(operation["operation_id"], succeeded=True)
                results.append((operation["operation_id"], "SUCCEEDED"))
            except Exception as error:
                self.repository.finish_operation(operation["operation_id"],
                                                 succeeded=False, error=error)
                results.append((operation["operation_id"], "FAILED"))
        return tuple(results)
