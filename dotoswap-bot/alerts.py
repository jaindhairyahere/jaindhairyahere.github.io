"""
Cross-platform desktop notification + sound alert helpers.

Everything degrades gracefully: if a notification backend isn't available,
we fall back to a console message so the tool still works everywhere.
"""

from __future__ import annotations

import sys
import webbrowser


def notify(title: str, message: str) -> None:
    """Show a desktop notification, falling back to console output."""
    shown = False

    # Preferred: plyer (cross-platform).
    try:
        from plyer import notification  # type: ignore

        notification.notify(title=title, message=message, timeout=15)
        shown = True
    except Exception:
        shown = False

    # Windows fallback via win10toast if plyer isn't usable.
    if not shown and sys.platform.startswith("win"):
        try:
            from win10toast import ToastNotifier  # type: ignore

            ToastNotifier().show_toast(title, message, duration=10, threaded=True)
            shown = True
        except Exception:
            shown = False

    # Always echo to the console as the last-resort, guaranteed channel.
    print(f"\n[ALERT] {title}: {message}\n")


def play_sound() -> None:
    """Play the 'Happy Birthday' melody as the alert. No-op if unavailable."""
    if sys.platform.startswith("win"):
        try:
            import time
            import winsound

            # Note frequencies (Hz).
            G4, A4, B4, C5, D5, E5, F5, G5 = 392, 440, 494, 523, 587, 659, 698, 784
            # Note durations (ms): eighth, quarter, half.
            E, Q, H = 180, 360, 680

            melody = [
                # Happy birthday to you
                (G4, E), (G4, E), (A4, Q), (G4, Q), (C5, Q), (B4, H),
                # Happy birthday to you
                (G4, E), (G4, E), (A4, Q), (G4, Q), (D5, Q), (C5, H),
                # Happy birthday dear ...
                (G4, E), (G4, E), (G5, Q), (E5, Q), (C5, Q), (B4, Q), (A4, H),
                # Happy birthday to you
                (F5, E), (F5, E), (E5, Q), (C5, Q), (D5, Q), (C5, H),
            ]

            for freq, duration in melody:
                winsound.Beep(freq, duration)
                time.sleep(0.03)  # tiny gap so repeated notes stay distinct
            return
        except Exception:
            pass

    # POSIX / fallback: terminal bell.
    try:
        for _ in range(3):
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        pass


def open_url(url: str) -> None:
    """Open the checkout URL in the default browser for manual completion."""
    try:
        webbrowser.open(url, new=2)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"[warn] could not open browser: {exc}")


def send_email(subject: str, body: str) -> None:
    """
    Send a plain-text notification email via personal Gmail SMTP.

    The password is read from config (which reads it from the environment /
    .env). If email is disabled or no password is configured, this is a no-op
    with a helpful log line — the other alerts still work.
    """
    import smtplib
    import ssl
    from email.message import EmailMessage

    import config

    if not getattr(config, "EMAIL_ENABLED", False):
        return

    if not config.SMTP_PASSWORD:
        print(
            "[warn] Email enabled but no SMTP password set. "
            "Create a .env with DOTOSWAP_SMTP_PASSWORD (a Gmail App Password). "
            "See .env.example. Skipping email."
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context) as server:
            server.login(config.EMAIL_FROM, config.SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[info] Notification email sent to {config.EMAIL_TO}.")
    except Exception as exc:
        print(f"[warn] Could not send email: {exc}")

