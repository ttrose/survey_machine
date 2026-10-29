"""Optional Cloudflare Email Service delivery for account invitations and resets."""

from html import escape
from urllib.parse import urlsplit


def _public_url(value: str) -> str | None:
    """Only use a configured HTTPS origin for links containing one-time tokens."""
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None
    return f"https://{parsed.netloc}"


async def deliver_account_email(request, *, recipient: str, name: str, activation_path: str, reset: bool) -> bool:
    """Return False when not configured or delivery fails, preserving manual-link fallback.

    Requires EMAIL_FROM, PUBLIC_APP_URL and an EMAIL binding in the Worker.
    Never log the activation token or other email contents.
    """
    env = request.scope.get("env")
    if env is None:
        return False
    sender = str(getattr(env, "EMAIL_FROM", "")).strip()
    origin = _public_url(str(getattr(env, "PUBLIC_APP_URL", "")))
    binding = getattr(env, "EMAIL", None)
    if not sender or not origin or binding is None:
        return False

    link = origin + activation_path
    action = "Reset your password" if reset else "Activate your account"
    subject = f"Survey Machine: {action}"
    plain = (
        f"Hello {name},\n\n"
        f"{action} using this one-time link:\n{link}\n\n"
        "This link expires in seven days. If you did not expect this email, ignore it."
    )
    html = (
        f"<p>Hello {escape(name)},</p>"
        f"<p>{escape(action)} using the link below:</p>"
        f'<p><a href="{escape(link, quote=True)}">{escape(action)}</a></p>'
        "<p>This link expires in seven days. If you did not expect this email, ignore it.</p>"
    )
    try:
        # Pyodide converts Python dictionaries to JavaScript objects using to_js.
        from js import Object
        from pyodide.ffi import to_js
        payload = to_js(
            {"from": sender, "to": recipient, "subject": subject, "text": plain, "html": html},
            dict_converter=Object.fromEntries,
        )
        await binding.send(payload)
    except Exception:
        # Keep the generated link usable for manual delivery if Cloudflare rejects
        # the message. The caller exposes only the success flag, not provider details.
        return False
    return True
