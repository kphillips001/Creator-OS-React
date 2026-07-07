import json
from pathlib import Path

import streamlit as st

from app.repositories.fanvue_account_repository import get_account_by_id
from app.services.fanvue_api_service import FanvueAPIService
from app.services.fanvue_oauth_service import FanvueOAuthService


OAUTH_SESSION_FILE = Path("data/config/fanvue_oauth_session.json")


def _save_oauth_session(data: dict):
    OAUTH_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    OAUTH_SESSION_FILE.write_text(json.dumps(data, indent=2))


def _load_oauth_session():
    if not OAUTH_SESSION_FILE.exists():
        return None

    try:
        return json.loads(OAUTH_SESSION_FILE.read_text())
    except Exception:
        return None


def _clear_oauth_session():
    if OAUTH_SESSION_FILE.exists():
        OAUTH_SESSION_FILE.unlink()


def _get_callback_code():
    code = st.query_params.get("code")
    return code[0] if isinstance(code, list) else code


def _normalize_identity(value):
    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace("@", "")
        .replace(".", "")
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _get_selected_account():
    account_id = st.session_state.get("fanvue_account_id")

    if not account_id:
        account_id = st.session_state.get("selected_fanvue_account_id")

    if not account_id:
        return None

    return get_account_by_id(int(account_id))


def _selected_label(selected_account: dict):
    return (
        selected_account.get("display_name")
        or selected_account.get("account_name")
        or selected_account.get("username")
        or f"Account #{selected_account.get('id')}"
    )


def _connected_label(connected_identity: dict):
    return (
        connected_identity.get("display_name")
        or connected_identity.get("displayName")
        or connected_identity.get("username")
        or connected_identity.get("handle")
        or connected_identity.get("uuid")
        or "Unknown provider account"
    )


def _extract_fanvue_identity(user_data: dict):
    if not user_data:
        return {}

    return {
        "uuid": user_data.get("uuid"),
        "username": (
            user_data.get("username")
            or user_data.get("handle")
            or user_data.get("slug")
        ),
        "display_name": (
            user_data.get("displayName")
            or user_data.get("display_name")
            or user_data.get("name")
        ),
        "raw": user_data,
    }


def _identity_matches_selected(selected_account: dict, connected_identity: dict):
    selected_username = _normalize_identity(selected_account.get("username"))
    selected_display_name = _normalize_identity(
        selected_account.get("display_name")
        or selected_account.get("account_name")
    )

    connected_username = _normalize_identity(connected_identity.get("username"))
    connected_display_name = _normalize_identity(
        connected_identity.get("display_name")
        or connected_identity.get("displayName")
    )

    if selected_username and connected_username:
        return selected_username == connected_username

    if selected_display_name and connected_display_name:
        return selected_display_name == connected_display_name

    return False


def _set_dashboard_account_state(account_id: int):
    st.session_state["fanvue_account_id"] = account_id
    st.session_state["selected_fanvue_account_id"] = account_id
    st.session_state["connected_fanvue_account_id"] = account_id
    st.session_state["dashboard_page"] = "Fanvue Auth"


def _set_disconnected_state():
    st.session_state["fanvue_connected"] = False
    st.session_state["fanvue_auth_status"] = "disconnected"


def _set_connected_state(selected_account: dict, connected_identity: dict):
    account_id = selected_account.get("id")

    st.session_state["fanvue_connected"] = True
    st.session_state["fanvue_auth_status"] = "connected"

    _set_dashboard_account_state(account_id)

    st.session_state["fanvue_user"] = connected_identity.get("raw") or connected_identity
    st.session_state["fanvue_user_uuid"] = connected_identity.get("uuid")
    st.session_state["fanvue_username"] = connected_identity.get("username")


def _set_mismatch_state():
    st.session_state["fanvue_connected"] = False
    st.session_state["fanvue_auth_status"] = "mismatch"


def _sync_connected_fanvue_user(selected_account: dict):
    if not selected_account:
        _set_disconnected_state()
        return {
            "connected": False,
            "matched": False,
            "reason": "missing_selected_account",
        }

    account_id = selected_account.get("id")

    try:
        api = FanvueAPIService(fanvue_account_id=account_id)
        user_result = api.get_current_user()
    except Exception as e:
        _set_disconnected_state()
        return {
            "connected": False,
            "matched": False,
            "reason": "fanvue_current_user_exception",
            "error": str(e),
            "selected_account": selected_account,
        }

    if not user_result or not user_result.get("success"):
        _set_disconnected_state()
        return {
            "connected": False,
            "matched": False,
            "reason": "fanvue_current_user_failed",
            "result": user_result,
            "selected_account": selected_account,
        }

    connected_identity = _extract_fanvue_identity(user_result.get("data") or {})
    matched = _identity_matches_selected(selected_account, connected_identity)

    if not matched:
        _set_mismatch_state()
        return {
            "connected": True,
            "matched": False,
            "reason": "account_mismatch",
            "selected_account": selected_account,
            "connected_identity": connected_identity,
        }

    _set_connected_state(
        selected_account=selected_account,
        connected_identity=connected_identity,
    )

    return {
        "connected": True,
        "matched": True,
        "reason": "matched",
        "selected_account": selected_account,
        "connected_identity": connected_identity,
    }


def _render_mismatch_warning(sync_result: dict):
    selected = sync_result.get("selected_account") or {}
    connected = sync_result.get("connected_identity") or {}

    st.warning(
        f"⚠️ Selected account is {_selected_label(selected)}, "
        f"but current provider OAuth session belongs to {_connected_label(connected)}."
    )

    st.caption("Please log into the correct provider account before reconnecting.")

    with st.expander("Debug OAuth identity mismatch"):
        st.write("Selected dashboard account:")
        st.json(selected)

        st.write("Connected provider account:")
        st.json(connected)


def _start_oauth_flow(oauth: FanvueOAuthService, selected_account: dict):
    result = oauth.generate_authorization_url()
    authorization_url = result.get("authorization_url")

    account_id = selected_account.get("id")
    _set_dashboard_account_state(account_id)

    _save_oauth_session(
        {
            "fanvue_account_id": account_id,
            "selected_account_name": _selected_label(selected_account),
            "authorization_url": authorization_url,
            "code_verifier": result.get("code_verifier"),
            "state": result.get("state"),
        }
    )

    st.info("Redirecting to provider authorization...")
    st.markdown(
        f"""
        If you are not redirected automatically,
        <a href="{authorization_url}" target="_self">click here to continue</a>.
        """,
        unsafe_allow_html=True,
    )


def render_fanvue_auth():
    st.markdown("## Provider Connections")
    st.caption("Connect the selected dashboard account to the matching provider OAuth account.")

    callback_code = _get_callback_code()

    if callback_code:
        st.info("Provider authorization detected. Saving connection...")

        session = _load_oauth_session()

        if not session:
            st.error("OAuth session not found. Click Connect Provider and try again.")
            return

        session_account_id = session.get("fanvue_account_id")

        if not session_account_id:
            st.error("OAuth session is missing the provider account ID.")
            return

        selected_account = get_account_by_id(int(session_account_id))

        if not selected_account:
            st.error("Could not restore the provider account used to start OAuth.")
            return

        selected_account_id = selected_account.get("id")
        _set_dashboard_account_state(selected_account_id)

        oauth = FanvueOAuthService(
            fanvue_account_id=selected_account_id,
        )

        st.info(f"Selected dashboard account: {_selected_label(selected_account)}")

        code_verifier = session.get("code_verifier")

        if not code_verifier:
            st.error("Missing OAuth verifier. Click Connect Provider and try again.")
            return

        result = oauth.exchange_code_for_tokens(
            code=callback_code.strip(),
            code_verifier=code_verifier,
        )

        if not result.get("success"):
            st.error("Provider token exchange failed.")
            st.json(result)
            return

        sync_result = _sync_connected_fanvue_user(selected_account)

        if sync_result.get("matched"):
            _clear_oauth_session()
            st.query_params.clear()
            st.success("Provider connected successfully ✅")

            connected = sync_result.get("connected_identity") or {}
            st.caption(f"Connected as: {_connected_label(connected)}")

            st.rerun()

        if sync_result.get("reason") == "account_mismatch":
            _render_mismatch_warning(sync_result)
            return

        st.error("Provider connected, but account validation failed.")
        st.json(sync_result)
        return

    selected_account = _get_selected_account()

    if not selected_account:
        st.warning("Select a dashboard provider account before connecting OAuth.")
        return

    selected_account_id = selected_account.get("id")

    oauth = FanvueOAuthService(
        fanvue_account_id=selected_account_id,
    )

    st.info(f"Selected dashboard account: {_selected_label(selected_account)}")

    st.divider()

    sync_result = _sync_connected_fanvue_user(selected_account)

    if sync_result.get("matched"):
        connected = sync_result.get("connected_identity") or {}
        st.success("Provider is already connected ✅")
        st.caption(f"Connected as: {_connected_label(connected)}")

        if connected.get("uuid"):
            st.caption(f"Account UUID: `{connected.get('uuid')}`")

        st.divider()

        if st.button("Reconnect Provider", use_container_width=True):
            try:
                _start_oauth_flow(oauth, selected_account)
            except Exception as e:
                st.error(f"Provider OAuth error: {e}")

        return

    if sync_result.get("reason") == "account_mismatch":
        _render_mismatch_warning(sync_result)
    else:
        st.info("No valid provider OAuth connection found for the selected dashboard account.")

    st.divider()

    if st.button("Connect Provider", use_container_width=True):
        try:
            _start_oauth_flow(oauth, selected_account)
        except Exception as e:
            st.error(f"Provider OAuth error: {e}")


