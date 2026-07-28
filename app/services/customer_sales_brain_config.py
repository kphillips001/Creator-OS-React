"""Central deterministic timing configuration for Customer Sales Brain."""
from dataclasses import dataclass
from datetime import timedelta
import os


@dataclass(frozen=True)
class CustomerSalesBrainConfig:
    purchase_cooldown: timedelta
    offer_nudge_delay: timedelta
    offer_expiration: timedelta

    @classmethod
    def from_environment(cls):
        return cls(
            purchase_cooldown=timedelta(hours=cls._hours(
                "CUSTOMER_SALES_PURCHASE_COOLDOWN_HOURS", 24
            )),
            offer_nudge_delay=timedelta(hours=cls._hours(
                "CUSTOMER_SALES_OFFER_NUDGE_HOURS", 24
            )),
            offer_expiration=timedelta(hours=cls._hours(
                "CUSTOMER_SALES_OFFER_EXPIRATION_HOURS", 72
            )),
        )

    @staticmethod
    def _hours(name, default):
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return max(1, value)
