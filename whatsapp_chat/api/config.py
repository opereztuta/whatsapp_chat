import frappe
from whatsapp_chat.api.auth import can_access_chat


@frappe.whitelist(allow_guest=True)
def settings(token=None):  # token kept only for backward-compat with JS calls
    user = frappe.session.user

    # Base config (safe for both System Users and Guests)
    config = {
        "socketio_port": frappe.conf.socketio_port,
        "user_email": user,
        "is_admin": False,
        "can_access_ui": False,
        "guest_title": "".join(frappe.get_hooks("guest_title")),
        "is_verified": False,
        "user": "Guest",
    }

    # HARD BLOCK: Guests never get chat UI
    if user == "Guest":
        config.update({
            "enable_chat": False,
            "chat_status": "Offline",
        })
        return config

    # System User / Desk logic
    user_type = frappe.db.get_value("User", user, "user_type")
    is_system_user = (user_type == "System User")
    can_access_ui = is_system_user and can_access_chat(user)

    config["is_admin"] = can_access_ui
    config["can_access_ui"] = can_access_ui

    # Merge chat settings (only relevant for authenticated users)
    config.update(get_chat_settings(can_access_ui))

    if config["is_admin"]:
        config["user"] = get_admin_name(user)
        config["user_settings"] = get_user_settings()

    return config


def get_admin_name(user_key):
    """Get the admin name for specified user key"""
    return frappe.db.get_value("User", user_key, "full_name")


def get_chat_settings(can_access_ui: bool):
    """
    Only enable the chat widget for authorized agents/system managers.
    Any other authenticated user (e.g. Website User) should not see the widget.
    """
    if not can_access_ui:
        return {
            "enable_chat": False,
            "chat_status": "Offline",
        }
    return {
        "enable_chat": True,
        "chat_status": "Online",
    }


def get_user_settings():
    return {
        "enable_message_tone": 1,
        "enable_notifications": 1,
    }
