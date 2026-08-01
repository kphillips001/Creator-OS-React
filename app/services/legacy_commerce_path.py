"""Explicit boundary for retired legacy CMS commerce execution."""


class LegacyCommercePathDisabledError(RuntimeError):
    def __init__(self):
        super().__init__(
            "Legacy CMS commerce publication is unavailable. Use canonical "
            "Commercial Offering publication and fulfillment."
        )


def disabled_legacy_commerce_path(*_args, **_kwargs):
    raise LegacyCommercePathDisabledError()

