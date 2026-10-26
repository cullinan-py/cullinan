from typing import TYPE_CHECKING

from cullinan import controller
from cullinan.web import get_api

if TYPE_CHECKING:
    from .services import InventoryService


@controller(url="/inventory")
class InventoryController:
    inventory_service: InventoryService  # ← constructor injection

    @get_api(url="/summary")
    def summary(self):
        return self.inventory_service.summary()
