from app.repositories.fanvue_account_repository import get_or_create_account


def test_account_repository():
    account = get_or_create_account(
        username="ava.blackthorne",
        display_name="Ava Blackthorne"
    )

    print("Account loaded/created successfully!")
    print(account)


if __name__ == "__main__":
    test_account_repository()