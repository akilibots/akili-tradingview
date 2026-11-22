<p align="center"><img src="https://raw.githubusercontent.com/akilibots/.github/main/assets/akilibots-icon.svg" width="144" alt="Akilibots"></p>

# Welcome to akili-tradingview!

[![Python 3.15.2](https://img.shields.io/badge/Python-3.15.2-6966FF?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![dYdX Chain](https://img.shields.io/badge/dYdX_Chain-0B0B18)](https://github.com/akilibots/akili-tradingview)
[![Docker tests](https://github.com/akilibots/akili-tradingview/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/akilibots/akili-tradingview/actions/workflows/tests.yaml)
[![Telegram](https://img.shields.io/badge/Telegram-community-6966FF?logo=telegram&logoColor=white)](https://t.me/+9F0CZj8emLc2YTY0)

> **Updated 22 November 2026:** dYdX Chain, Python 3.15.2, refreshed dependencies, durable order recovery and Docker regression tests. Alerts now enter a durable queue before exchange processing.

Jambo! and welcome! **akili-tradingview** connects your TradingView alerts to dYdX Chain. If you can set an alert for your idea, you can use it to trigger an order. 📺

The word **akili** means brain or mind in Swahili. These bots are non-opinionated: you set the strategy and stay in control. They grew out of wanting that little extra tweak that commercial bots always seemed to miss.

## Get it running

You need Git, Docker with Compose, and a funded dYdX **Chain testnet** wallet to
use the supplied example. The bot needs the wallet's mnemonic and a matching
Chain address. Old v3 API keys, STARK keys and v3 state do not work here.

1. Clone the repository and create your environment file:

```sh
git clone https://github.com/akilibots/akili-tradingview.git
cd akili-tradingview
cp .env.example .env
```

2. Edit `.env`. Set `DYDX_MNEMONIC` to your Chain wallet's mnemonic, in quotes.
   Leave the Telegram values empty if you do not want notifications.
3. Edit [`data/strategy.json`](data/strategy.json). Set `exchange.address` to that
   wallet's address, check its subaccount and review the strategy quantities and
   prices. The sample endpoints select **testnet**.
4. Set `WEBHOOK_SECRET` and review `ALLOWED_IPS` in `.env`. Configure an HTTPS reverse proxy as described below.

5. Build and start the bot:

```sh
docker compose up --build -d
docker compose logs -f
```

To stop it:

```sh
docker compose down
```

Stopping the process leaves its exchange orders in place. Check and cancel those
orders separately when needed. Do not run two instances from the same data folder.

## Connect your alerts

The service runs under Waitress on port 8080. Terminate HTTPS at a reverse proxy and forward to the local service.

Set `WEBHOOK_SECRET` in `.env`. Each JSON alert must include the matching `secret`,
or send it as an `Authorization: Bearer ...` header. Source addresses must also
appear in the comma-separated `ALLOWED_IPS`. The example contains TradingView's
published webhook addresses. Behind a proxy, allow its actual peer address and
restrict access at that proxy. The application does not trust forwarded-IP headers.
`ALLOWED_IPS=*` disables the source-address filter but still requires the secret.

POST `/place` with:

```json
{"secret":"YOUR_WEBHOOK_SECRET","ref":"t12","reset":["t13","t14"],"market":"SOL-USD","side":"buy","price":16,"size":10,"multiple":false}
```

`ref` and reset references contain 1 to 64 letters, digits, underscores or hyphens.
All tracked orders under each reset reference are cancelled before placement.
Missing reset references are harmless. `multiple=false` returns the previous
order without submitting again. `multiple=true` permits additional orders under
the same reference, all of which remain cancellable. Deduplication persists
across restarts. `till` is an optional future Unix timestamp, 60 seconds to 95 days
ahead. Omitting it gives a rolling 24-hour expiry.

POST `/cancel` with:

```json
{"secret":"YOUR_WEBHOOK_SECRET","orders":["t12","t13"]}
```

Valid alerts and cancellations are saved to `data/jobs.sqlite3` and return JSON
with a job `id` and HTTP 202 immediately, within TradingView's short request
window. A single worker performs exchange operations in queue order. Poll
`GET /jobs/ID` using the bearer header to see `queued`, `processing`, `done` or
`failed` and its result. A failed job blocks later jobs for reconciliation;
inspect its saved error and exchange state before retrying it. Keep the queue
database with the JSON state and exchange journal when backing up or recovering.

Invalid payloads return 400; unauthorized sources or secrets return 403.
Processing interrupted by a restart resumes with the same job and client IDs,
including alerts with `multiple=true`. Use one server process per data directory.
The receiving HTTPS endpoint must use port 443 or 80; the internal service listens
on 8080. See [TradingView webhook documentation](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/).

## Configuration notes

| Setting | What to check |
| --- | --- |
| Alert `market` | The perpetual market for each alert, such as `SOL-USD` |
| `exchange.address` | The Chain address matching `DYDX_MNEMONIC` |
| `exchange.subaccount` | A cross-margin subaccount from 0 to 127, with collateral |
| `exchange.network` | `testnet` or `mainnet` |
| `exchange.indexer`, `websocket`, `node` | Endpoints for the same selected network |

The node value is a TLS gRPC host and port, without `http://` or `https://`.
Review market sizes and prices before running any sample. Quantities are in the
base asset, not a dollar budget. To use mainnet, change the network and all its
endpoints together and configure the corresponding wallet and collateral.

You can supply JSON5 through the `strategy` environment variable instead of the
strategy file. Settings are tied to saved strategy state; reconcile existing
orders before changing an active strategy. Telegram notifications use
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.

## Restarting and recovery

Compose mounts `./data`, so state survives a container replacement.
`data/state.json` records progress and `data/exchange.json` records client IDs
before order submission. Keep them together and keep them out of Git.
Also keep `data/jobs.sqlite3` and any SQLite journal files with that backup.

An uncertain submission is checked using its existing client ID. The bot does not
turn a timeout into a second trade. If it cannot reconcile an order, it stops so
you can inspect the exchange and saved state. Do not delete state to bypass an
error. Partial-fill and cancellation handling is described above.

For a v3 migration, reconcile old orders and positions first, archive the old
state, then start with a fresh data folder. Use a separate data folder and
subaccount for each strategy. Never commit wallet mnemonics or `.env`.

Limit orders use Chain long-term orders with a default 24-hour expiry. Prices
follow market ticks and sizes must be exact multiples of `stepSize`. Market
orders use short-term IOC orders with a slippage bound. Profit figures, where
reported, include actual fill prices and trading fees, but exclude funding,
network transaction fees and unrealised positions.

## Test it yourself

```sh
docker build --target test -t bot-test .
docker run --rm --network none bot-test
```

The suite uses simulated exchange responses with networking disabled. It covers
order handling and recovery; SDK checks also build and sign transactions locally.
Passing tests is not a promise of live execution or profitable trading.

<details>
<summary>Running directly with Python</summary>

Use Python 3.15.2 and install the native C/C++ and Rust build tools required by
the wallet dependencies. Docker includes these prerequisites in its build stage.

```sh
python3 -m venv .venv
. .venv/bin/activate
PIP_BUILD_CONSTRAINT="$PWD/build-constraints.txt" python3 -m pip install -r requirements-dev.txt
python3 -m pip check
```

Export the values from `.env` into your shell, then run `python3 run.py`.
The direct Python entrypoint does not automatically read `.env`.
The dYdX SDK constrains some signing packages to older compatible versions;
`build-constraints.txt` supplies the build tools those packages require.

</details>

## The usual bit

This software is for educational purposes only. Do not risk money you are afraid
to lose. **USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME
NO RESPONSIBILITY FOR YOUR TRADING RESULTS.**

See [LICENSE](LICENSE) for the full terms.

Part of [Akilibots](https://github.com/akilibots). Come say jambo in [Telegram](https://t.me/+9F0CZj8emLc2YTY0).
