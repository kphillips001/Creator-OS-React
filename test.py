from telethon.sync import TelegramClient

api_id = 30319536
api_hash = "4ae7522a90bdd73398d545fe2b8f915c"

with TelegramClient("session", api_id, api_hash) as client:
    for dialog in client.iter_dialogs():
        print(dialog.name, dialog.id)