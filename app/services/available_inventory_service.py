"""Read-only application service for Available Inventory."""

from app.repositories.available_inventory_repository import AvailableInventoryRepository


class AvailableInventoryService:
    def __init__(self, repository: AvailableInventoryRepository | None = None) -> None:
        self.repository = repository or AvailableInventoryRepository()

    def list_page(self, **filters):
        return self.repository.list_page(**filters)
