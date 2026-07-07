from app.repositories.content_ownership_repository import (
    get_owned_content_tags,
    user_already_owns_content,
)


class ContentOwnershipService:
    """
    3D.16 Centralized ownership intelligence layer.

    Section 6 hardened:
    Ownership checks must always be scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    def get_owned_content_tags(
        self,
        fanvue_account_id: int,
        fanvue_user_id,
    ):
        return get_owned_content_tags(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

    def user_already_owns_content(
        self,
        fanvue_account_id: int,
        fanvue_user_id,
        content_tag: str,
    ):
        return user_already_owns_content(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            content_tag=content_tag,
        )