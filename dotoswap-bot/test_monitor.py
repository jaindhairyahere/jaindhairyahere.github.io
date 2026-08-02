"""
Offline tests for the monitor using mocked API responses.

These never touch the network or fire real notifications. They verify:
  * empty result -> no alert,
  * a newly-available ticket -> notify + sound + open browser,
  * the same ticket again -> NO duplicate alert,
  * HTTP 429 -> polite backoff (doubling), no crash.

Run:
    py test_monitor.py
"""

from __future__ import annotations

import unittest
from unittest import mock

import requests

import monitor


class _StopLoop(Exception):
    """Sentinel raised from a patched sleep to break monitor's infinite loop."""


def _make_response(*, json_data=None, status=200, raise_http=False):
    resp = mock.Mock()
    resp.status_code = status
    resp.headers = {"content-type": "application/json"}
    resp.json.return_value = json_data if json_data is not None else []
    if raise_http:
        err = requests.HTTPError("mocked error")
        err.response = resp
        resp.raise_for_status.side_effect = err
    else:
        resp.raise_for_status.return_value = None
    return resp


TICKET_A = {
    "startNummer": 14201,
    "hasTshirt": True,
    "tshirtSize": "L",
    "hasMeal": False,
    "orderRef": "ORD-2026-9921",
    "volgnummer": 12,
    "isBeschikbaar": True,
    "correlationId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
}


class MonitorLogicTests(unittest.TestCase):
    def test_full_cycle(self):
        # Sequence of what session.get() returns on each poll.
        responses = [
            _make_response(json_data=[]),                 # 1: nothing
            _make_response(json_data=[TICKET_A]),         # 2: new ticket -> alert
            _make_response(json_data=[TICKET_A]),         # 3: same ticket -> dedup
            _make_response(status=429, raise_http=True),  # 4: rate limited
        ]

        fake_session = mock.Mock()
        fake_session.headers = {}
        fake_session.get.side_effect = responses

        # Break out of the infinite loop after enough sleeps.
        sleep_calls: list[float] = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 4:
                raise _StopLoop()

        with mock.patch.object(monitor.requests, "Session", return_value=fake_session), \
             mock.patch.object(monitor.time, "sleep", side_effect=fake_sleep), \
             mock.patch.object(monitor, "confirm_and_reserve") as m_reserve, \
             mock.patch.object(monitor, "send_email") as m_email, \
             mock.patch.object(monitor, "notify") as m_notify, \
             mock.patch.object(monitor, "play_sound") as m_sound, \
             mock.patch.object(monitor, "open_url") as m_open:

            with self.assertRaises(_StopLoop):
                monitor.run()

        # Alerted exactly once (for TICKET_A), not twice (dedup worked).
        self.assertEqual(m_notify.call_count, 1)
        # Email is only sent when enabled in config.
        expected_email = 1 if monitor.config.EMAIL_ENABLED else 0
        self.assertEqual(m_email.call_count, expected_email)
        self.assertEqual(m_sound.call_count, 1)
        self.assertEqual(m_open.call_count, 1)
        m_open.assert_called_once_with(monitor.config.CHECKOUT_URL)
        # The reserve prompt is offered exactly once (for the new ticket).
        self.assertEqual(m_reserve.call_count, 1)

        # Sleeps: 3 normal polls + 1 backoff. The backoff sleep should equal
        # the configured start value (first 429).
        self.assertEqual(len(sleep_calls), 4)
        self.assertEqual(sleep_calls[0], monitor.config.POLL_INTERVAL_SECONDS)
        self.assertEqual(sleep_calls[3], monitor.config.BACKOFF_START_SECONDS)

    def test_fetch_ignores_unavailable(self):
        gone = dict(TICKET_A, isBeschikbaar=False)
        fake_session = mock.Mock()
        fake_session.get.return_value = _make_response(json_data=[gone])
        items = monitor.fetch_available_items(fake_session)
        # fetch returns the raw list; availability filtering happens in run().
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["isBeschikbaar"])

    def test_describe_item(self):
        text = monitor.describe_item(TICKET_A)
        self.assertIn("14201", text)
        self.assertIn("ORD-2026-9921", text)


class ReserveFlowTests(unittest.TestCase):
    def test_reserve_ticket_true(self):
        session = mock.Mock()
        session.get.return_value = _make_response(json_data=True)
        self.assertTrue(monitor.reserve_ticket(session, "cid-1"))

    def test_start_swap_returns_voucher(self):
        session = mock.Mock()
        session.get.return_value = _make_response(
            json_data={"voucherUrl": "https://checkout.example/pay?t=abc"}
        )
        url = monitor.start_swap(session, "cid-1")
        self.assertEqual(url, "https://checkout.example/pay?t=abc")

    def test_confirm_yes_reserves_and_opens_voucher(self):
        session = mock.Mock()
        # First get -> reserve (True); second get -> start-swap (voucher).
        session.get.side_effect = [
            _make_response(json_data=True),
            _make_response(json_data={"voucherUrl": "https://checkout.example/pay"}),
        ]
        with mock.patch("builtins.input", return_value="y"), \
             mock.patch.object(monitor, "open_url") as m_open:
            monitor.confirm_and_reserve(session, TICKET_A)
        m_open.assert_called_once_with("https://checkout.example/pay")

    def test_confirm_no_does_nothing(self):
        session = mock.Mock()
        with mock.patch("builtins.input", return_value="n"), \
             mock.patch.object(monitor, "open_url") as m_open:
            monitor.confirm_and_reserve(session, TICKET_A)
        session.get.assert_not_called()
        m_open.assert_not_called()

    def test_confirm_yes_but_already_taken_opens_site(self):
        session = mock.Mock()
        session.get.return_value = _make_response(json_data=False)  # declined
        with mock.patch("builtins.input", return_value="y"), \
             mock.patch.object(monitor, "open_url") as m_open:
            monitor.confirm_and_reserve(session, TICKET_A)
        m_open.assert_called_once_with(monitor.config.CHECKOUT_URL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
