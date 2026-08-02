"""
DotoSwap availability monitor.

Polls the public marketplace listing at a fixed, respectful interval and
alerts you (desktop notification + sound + opens the site) when one or more
tickets become available so you can complete the purchase manually.

Design principles:
  * Respectful, fixed-rate polling.
  * Polite exponential backoff on HTTP 429 (never routes around it).
  * Honest User-Agent; no browser spoofing, no bot-detection evasion.
  * The human always completes the checkout.

Run:
    python monitor.py
Stop with Ctrl+C.
"""

from __future__ import annotations

import signal
import sys
import time
from datetime import datetime

import requests

import config
from alerts import notify, open_url, play_sound, send_email


def _log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}")


def fetch_available_items(session: requests.Session) -> list[dict]:
    """
    Query the public 'available items' endpoint.

    Returns the parsed list on success. Raises requests.HTTPError with the
    status attached so the caller can handle 429 specially.
    """
    url = config.BASE_URL + config.AVAILABLE_ITEMS_PATH
    response = session.get(url, timeout=config.REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, list):
        _log(f"unexpected response shape (not a list): {type(data).__name__}")
        return []
    return data


def describe_item(item: dict) -> str:
    """Human-readable one-liner for a marketplace item."""
    start = item.get("startNummer", "?")
    tshirt = item.get("tshirtSize") if item.get("hasTshirt") else "no"
    meal = "meal" if item.get("hasMeal") else "no-meal"
    ref = item.get("orderRef", "?")
    return f"#{start} (tshirt: {tshirt}, {meal}, ref: {ref})"


def reserve_ticket(session: requests.Session, correlation_id: str) -> bool:
    """
    Call the documented reserve endpoint exactly ONCE.

    This is only ever invoked after an explicit human 'y' confirmation.
    Returns True if the server confirms the reservation.
    """
    url = config.BASE_URL + config.RESERVE_PATH
    response = session.get(
        url,
        params={"correlationId": correlation_id},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json() is True


def start_swap(session: requests.Session, correlation_id: str) -> str | None:
    """
    Call the documented start-swap endpoint once and return the voucher URL
    so the human can complete payment themselves.
    """
    url = config.BASE_URL + config.START_SWAP_PATH
    response = session.get(
        url,
        params={"correlationId": correlation_id},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return data.get("voucherUrl")
    return None


def confirm_and_reserve(session: requests.Session, item: dict) -> None:
    """
    Ask the human to confirm, then do a single reserve + start-swap and open
    the checkout voucher for them to pay. No retries, no racing loop.

    Polling is paused while we wait for your keypress — that's intentional:
    once a ticket is found, the decision is yours to make.
    """
    correlation_id = item.get("correlationId")
    if not correlation_id:
        _log("Item has no correlationId; open the site to reserve manually.")
        open_url(config.CHECKOUT_URL)
        return

    try:
        answer = input(
            f"Reserve ticket {describe_item(item)} now? [y/N] "
        ).strip().lower()
    except EOFError:
        answer = "n"

    if answer != "y":
        _log("Not reserving. Continuing to monitor.")
        return

    try:
        reserved = reserve_ticket(session, correlation_id)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        _log(
            f"Reserve call failed (HTTP {status}) — likely already claimed. "
            "Opening the site so you can try manually."
        )
        open_url(config.CHECKOUT_URL)
        return

    if not reserved:
        _log("Server declined the reservation (already taken). Opening the site.")
        open_url(config.CHECKOUT_URL)
        return

    _log("Reserved. Fetching your checkout voucher...")
    try:
        voucher_url = start_swap(session, correlation_id)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        _log(
            f"Reserved, but start-swap failed (HTTP {status}). "
            "Opening the swap site so you can finish there."
        )
        open_url(config.CHECKOUT_URL)
        return

    target = voucher_url or config.CHECKOUT_URL
    _log(f"Opening checkout — complete payment yourself: {target}")
    open_url(target)


def run() -> None:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }
    )

    # Track which tickets we've already alerted on, so we don't spam.
    already_alerted: set[str] = set()
    backoff = config.BACKOFF_START_SECONDS

    _log("DotoSwap availability monitor started.")
    _log(
        f"Polling every {config.POLL_INTERVAL_SECONDS}s. "
        "Respectful mode: backs off on 429, no browser spoofing. "
        "Press Ctrl+C to stop."
    )

    while True:
        try:
            items = fetch_available_items(session)
            # Successful request -> reset any accumulated backoff.
            backoff = config.BACKOFF_START_SECONDS

            available = [it for it in items if it.get("isBeschikbaar", True)]

            if not available:
                _log("No tickets available.")
            else:
                # Only alert on tickets we haven't announced yet.
                new_items = [
                    it
                    for it in available
                    if str(it.get("correlationId") or it.get("startNummer"))
                    not in already_alerted
                ]

                if new_items:
                    summary = ", ".join(describe_item(it) for it in new_items[:5])
                    _log(f"TICKET(S) AVAILABLE: {summary}")

                    notify(
                        "DotoSwap: ticket available",
                        f"{len(new_items)} ticket(s) open — go complete checkout: {summary}",
                    )
                    if config.EMAIL_ENABLED:
                        send_email(
                            "DotoSwap: ticket available",
                            f"{len(new_items)} ticket(s) available now:\n\n{summary}\n\n"
                            f"Open: {config.CHECKOUT_URL}",
                        )
                    if config.PLAY_SOUND_ON_HIT:
                        play_sound()
                    if config.OPEN_BROWSER_ON_HIT:
                        open_url(config.CHECKOUT_URL)

                    for it in new_items:
                        already_alerted.add(
                            str(it.get("correlationId") or it.get("startNummer"))
                        )

                    # Human-confirmed one-click reserve for the first new hit.
                    if config.ENABLE_ONE_CLICK_RESERVE:
                        confirm_and_reserve(session, new_items[0])
                else:
                    _log(
                        f"{len(available)} ticket(s) still listed "
                        "(already alerted; not re-notifying)."
                    )

            time.sleep(config.POLL_INTERVAL_SECONDS)

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 429:
                _log(
                    f"Rate limited (429). Backing off for {backoff}s "
                    "(respecting the server)."
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, config.BACKOFF_MAX_SECONDS)
            else:
                _log(f"HTTP error {status}; retrying next cycle.")
                time.sleep(config.POLL_INTERVAL_SECONDS)

        except requests.RequestException as exc:
            _log(f"Network error: {exc}. Retrying next cycle.")
            time.sleep(config.POLL_INTERVAL_SECONDS)


def _handle_sigint(signum, frame):  # noqa: ARG001
    _log("Shutting down. Bye!")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_sigint)
    run()
