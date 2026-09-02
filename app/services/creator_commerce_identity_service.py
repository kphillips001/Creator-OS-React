"""Canonical Creator commerce identity resolution."""


def resolve_fanvue_account_id(creator_profile: dict, requested_account_id=None) -> int:
    """Resolve the configured Fanvue account, preserving legacy trusted overrides."""
    account_id = requested_account_id or creator_profile.get("fanvue_account_id")
    if not account_id:
        raise ValueError("A connected Fanvue account is required.")
    return int(account_id)
