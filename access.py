"""Identity-based instructor authorization. No shared passwords or client role flags."""
import os
import streamlit as st


def local_mode() -> bool:
    # Older launchers remain compatible; an explicit Lattice setting takes precedence.
    return os.environ.get("LATTICE_LOCAL_MODE", os.environ.get("CATALYST_LOCAL_MODE")) == "1"


def settings() -> dict:
    try:
        return dict(st.secrets.get("access", {}))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return {}


def identity() -> dict:
    user = getattr(st, "user", None)
    if user is not None and getattr(user, "is_logged_in", False):
        return dict(user)
    return {}


def authorized_instructor(user: dict, configuration: dict) -> bool:
    email = str(user.get("email", "")).casefold()
    return bool(user.get("email_verified") is True and email and
                email in {str(e).casefold() for e in configuration.get("instructor_emails", [])})


def is_instructor() -> bool:
    return authorized_instructor(identity(), settings())


def storage_owner() -> str:
    user = identity()
    if user.get("sub"):
        return f"oidc:{user.get('iss', '')}:{user['sub']}"
    return "local-workstation" if local_mode() else ""


def render_account() -> None:
    with st.sidebar.expander("Account & access"):
        user = identity()
        if user:
            st.caption("Instructor" if is_instructor() else "Student")
            if st.button("Sign out"):
                st.session_state.clear()
                st.logout()
        else:
            try:
                configured = bool(st.secrets.get("auth", {}).get("client_id"))
            except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
                configured = False
            if configured:
                if st.button("Sign in"):
                    st.login()
            else:
                st.caption("Student view. Instructor sign-in requires institutional OIDC configuration.")
        if local_mode():
            st.caption("Local project storage enabled on this computer.")
