# Technical Specification & Architecture Document

**Project:** DotoSwap Automated Lock-Renewal & Ticket Reservation System

**Target Audience:** Development / AI Coding Assistant (Claude Code)

---

## 1. Problem Statement

Securing a participation ticket on the DotoSwap marketplace for the Dodentocht event is a high-concurrency race condition. Available tickets are surfaced to the public pool and claimed within seconds. While standard API polling can detect available tickets, completing the purchase requires an authenticated, browser-based checkout flow (capturing session cookies, CSRF tokens, and handling external payment redirects).

A standard script fails at the handoff stage, whereas a manual user cannot race the initial server lock. Furthermore, server-side locks expire in 15 minutes, causing uncompleted ticket purchases to "rebound" back into the public pool.

---

## 2. System Architecture & Constraints

* **Lock TTL:** Calling the reservation endpoint acquires an atomic server-side lock with a **15-minute Time-To-Live (TTL)**.
* **The Rebound Effect:** If a user fails to finalize payment within 15 minutes, the server drops the lock, releasing the ticket back to the public pool at $T_0 + 15\text{ minutes}$.
* **Dual-Process Architecture (Leader-Follower):**
* **Leader:** Polls the public endpoint at a safe rate ($2\text{ req/min}$), acquires the initial lock, fires system alerts, and opens the Playwright browser window for human execution.
* **Follower:** Remains dormant during the active lock period, then executes targeted high-frequency polling ($1\text{ req/1.5s}$) during the $T_0 + 14:50 \rightarrow 15:10$ window to reclaim the lock if the payment was abandoned.


* **Zero-Trust Execution:** All requests must route through Playwright's integrated HTTP client (`page.request`) to inherit valid browser headers, cookies, and CORS parameters naturally.

---

## 3. Detailed API Endpoint Specification

**Base URL:**

`[https://swapbff20250715042304-dvcbfgdjfkcbakaz.westeurope-01.azurewebsites.net/api](https://swapbff20250715042304-dvcbfgdjfkcbakaz.westeurope-01.azurewebsites.net/api)`

### Required Request Headers

```http
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Accept: application/json, text/plain, */*
Content-Type: application/json

```

---

### Endpoint Catalog

#### 1. Fetch Available Marketplace Items

* **Endpoint:** `GET /Marktplaats/getBeschikbareMarktplaatsItems`
* **Purpose:** Queries the public pool of available tickets.
* **Authentication:** Public / Session Cookie
* **Response Payload Structure (`HTTP 200`):**

```json
[
  {
    "startNummer": 14201,
    "hasTshirt": true,
    "tshirtSize": "L",
    "hasMeal": false,
    "orderRef": "ORD-2026-9921",
    "volgnummer": 12,
    "isBeschikbaar": true,
    "correlationId": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
]

```

#### 2. Reserve Ticket (Acquire Lock)

* **Endpoint:** `GET /Marktplaats/reserveerTicket?correlationId={correlationId}`
* **Purpose:** Claims an atomic server-side lock on the target ticket for 15 minutes.
* **URL Parameter:** `correlationId` (String, Required)
* **Response Payload Structure (`HTTP 200`):**

```json
true

```

*(Returns `false` or `HTTP 400/404` if the ticket has already been claimed by another client).*

#### 3. Initiate Swap / Fetch Voucher URL

* **Endpoint:** `GET /Marktplaats/startSwapVanMarktplaats?correlationId={correlationId}`
* **Purpose:** Finalizes the marketplace swap transaction and retrieves the checkout/registration URL.
* **URL Parameter:** `correlationId` (String, Required)
* **Response Payload Structure (`HTTP 200`):**

```json
{
  "voucherUrl": "https://registration.dodentocht.be/checkout?token=eyJhbGciOi..."
}

```

#### 4. Release Reservation Lock (Undo)

* **Endpoint:** `GET /Marktplaats/reserveringOngedaanMaken?correlationId={correlationId}`
* **Purpose:** Explicitly releases the server-side lock, returning the ticket to the public pool.
* **URL Parameter:** `correlationId` (String, Required)
* **Response Payload Structure (`HTTP 200`):**

```json
true

```

---

## 4. Leader-Follower State Machine Specification

```
                  +-----------------------------------+
                  |           STATE 1: HUNT           |
                  | (Leader: 30s poll / Follower: off)|
                  +-----------------+-----------------+
                                    |
                         Ticket Found & Reserved
                                    |
                                    v
                  +-----------------------------------+
                  |          STATE 2: HANDOFF         |
                  | (Lock acquired, Alert, OS Sound)  |
                  +-----------------+-----------------+
                                    |
                        User Inaction / Timeout
                                    |
                                    v
                  +-----------------------------------+
                  |         STATE 3: SNIPER           |
                  | (Follower wakes at T_0 + 14m 50s) |
                  +-----------------+-----------------+
                                    |
                     +--------------+--------------+
                     |                             |
             Rebound Captured                Rebound Missed / Purchased
                     |                             |
                     v                             v
       +----------------------------+    +-------------------+
       |      STATE 4: SWAP         |    |  STATE 5: RESET   |
       | (Follower becomes Leader)  |    | (Reset to State 1)|
       +----------------------------+    +-------------------+

```

### State Breakdown

| State | Role Active | Interval | Primary Action | Exit Condition |
| --- | --- | --- | --- | --- |
| **State 1: Hunt** | Leader | $30\text{ seconds}$ | Query `getBeschikbareMarktplaatsItems` | `items.length > 0` |
| **State 2: Handoff** | Leader | N/A | Call `reserveerTicket`, trigger system beep, bring Playwright window to front | User completes form OR $14.8\text{ min}$ elapse |
| **State 3: Sniper** | Follower | $1.5\text{ seconds}$ | Sleep until $T_0 + 14:50$, then poll specifically for target `correlationId` | Target `correlationId` reappears OR $T_0 + 16:00$ reached |
| **State 4: Swap** | Follower | Immediate | Call `reserveerTicket`, sound alarm, swap Leader/Follower roles | Transition to **State 2** |
| **State 5: Reset** | Both | N/A | Clear active `correlationId` and timer state | Transition to **State 1** |

---

## 5. Technical Implementation Requirements for Claude Code

### Environment & Dependencies

* **Language:** Python 3.10+
* **Libraries:** `playwright`, `asyncio`, `logging`
* **System Tools (Linux):** `notify-send`, `paplay` / `aplay` (for audio alerts)

### Code Structure Requirements

1. **Playwright Integration:**
* Run Playwright with `headless=False`.
* Use `page.request.get()` for all API calls to ensure cookies and CORS context match the browser window.


2. **Alert Routine:**
```python
import subprocess

def trigger_alarm(msg: str):
    subprocess.run(["notify-send", "-u", "critical", "DotoSwap Alert", msg])
    # Play standard system sound loop
    subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"])

```


3. **Concurrency & Control Flow:**
* Implement main asynchronous loop using `asyncio.sleep()`.
* Do not block the event loop while waiting for human input in State 2; use an asynchronous event (`asyncio.Event()`) or non-blocking console prompt.
* Intercept HTTP status code `429` (Rate Limited) globally; if encountered, double the polling sleep time for 3 minutes before resuming normal speed.