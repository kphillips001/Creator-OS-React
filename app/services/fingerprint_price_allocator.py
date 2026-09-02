"""Pure nearest-price allocation policy for private-chat bootstrap offers."""
from dataclasses import dataclass


class FingerprintPoolExhaustedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FingerprintPricePolicy:
    provider_minimum_minor: int = 300
    provider_maximum_minor: int = 50000

    @staticmethod
    def maximum_delta(base_price_minor: int) -> int:
        if base_price_minor < 1000:
            band = 25
        elif base_price_minor < 2500:
            band = 50
        else:
            band = 100
        five_percent = max(1, base_price_minor * 5 // 100)
        return min(band, five_percent)

    def candidates(self, base_price_minor: int):
        delta = self.maximum_delta(base_price_minor)
        for offset in range(1, delta + 1):
            lower = base_price_minor - offset
            upper = base_price_minor + offset
            if lower >= self.provider_minimum_minor:
                yield lower
            if upper <= self.provider_maximum_minor:
                yield upper

    def select(self, base_price_minor: int, *, excluded_prices) -> int:
        excluded = {int(value) for value in excluded_prices}
        for candidate in self.candidates(int(base_price_minor)):
            if candidate not in excluded:
                return candidate
        raise FingerprintPoolExhaustedError(
            "No permanently unique fingerprint price remains in the fairness band."
        )
