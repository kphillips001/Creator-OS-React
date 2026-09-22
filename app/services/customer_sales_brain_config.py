"""Central deterministic timing configuration for Customer Sales Brain."""
from dataclasses import dataclass
from datetime import timedelta
import os


@dataclass(frozen=True)
class CustomerSalesBrainConfig:
    purchase_cooldown: timedelta
    offer_nudge_delay: timedelta
    offer_expiration: timedelta
    photoshoot_objection_recovery_limit: int = 2
    sexual_receptiveness_min_engagements: int = 4
    sexual_receptiveness_min_history_turns: int = 3
    sexual_sales_cooldown: timedelta = timedelta(hours=72)
    sexual_sales_max_opportunities: int = 3
    sexual_sales_episode_separation: timedelta = timedelta(hours=6)
    time_waster_min_failed_presentations: int = 8

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
            photoshoot_objection_recovery_limit=cls._positive_int(
                "PHOTOSHOOT_OBJECTION_RECOVERY_LIMIT", 2
            ),
            sexual_receptiveness_min_engagements=cls._positive_int(
                "CUSTOMER_SALES_SEXUAL_RECEPTIVENESS_MIN_ENGAGEMENTS", 4
            ),
            sexual_receptiveness_min_history_turns=cls._positive_int(
                "CUSTOMER_SALES_SEXUAL_RECEPTIVENESS_MIN_HISTORY_TURNS", 3
            ),
            sexual_sales_cooldown=timedelta(hours=cls._hours(
                "CUSTOMER_SALES_SEXUAL_COOLDOWN_HOURS", 72
            )),
            sexual_sales_max_opportunities=cls._positive_int(
                "CUSTOMER_SALES_SEXUAL_MAX_OPPORTUNITIES", 3
            ),
            sexual_sales_episode_separation=timedelta(hours=cls._hours(
                "CUSTOMER_SALES_SEXUAL_EPISODE_SEPARATION_HOURS", 6
            )),
            time_waster_min_failed_presentations=cls._positive_int(
                "CUSTOMER_SALES_TIME_WASTER_MIN_FAILED_PRESENTATIONS", 8
            ),
        )

    @staticmethod
    def _hours(name, default):
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return max(1, value)

    @staticmethod
    def _positive_int(name, default):
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return max(1, value)
