import pytest
import sys
from types import SimpleNamespace


def test_cli_simulator_refuses_a_production_database(monkeypatch):
    from app import database
    from app import main

    monkeypatch.setattr(database, "DATABASE_URL", "postgresql://local/fanvue_chatbot")
    with pytest.raises(ValueError, match="test-scoped"):
        main.start_app()


def test_dashboard_simulator_refuses_a_production_database(monkeypatch):
    from app import database
    monkeypatch.setitem(sys.modules, "streamlit", SimpleNamespace(session_state={}))
    from app.dashboard.pages import chat_console

    monkeypatch.setattr(database, "DATABASE_URL", "postgresql://local/fanvue_chatbot")
    with pytest.raises(ValueError, match="test-scoped"):
        chat_console._get_simulator_context()
