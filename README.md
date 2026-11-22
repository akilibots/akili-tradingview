# akili-tradingview

Authenticated TradingView webhooks that place dYdX Chain limit orders.

The Flask application runs under Waitress on port 8080. Terminate HTTPS at a
reverse proxy and forward to the local service. Flask debug mode and temporary
self-signed server certificates are not used.

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

## Requirements and configuration

Docker builds use Python 3.15.2. Copy `.env.example` to `.env`, set
`DYDX_MNEMONIC` to the mnemonic of a dYdX Chain wallet, then edit
`data/strategy.json`. The wallet must match `exchange.address` and have collateral
in the configured cross-margin subaccount. A v3 API key or STARK key cannot be used.
Never commit `.env`, a wallet mnemonic, or runtime state.

The example selects **testnet**. Set `exchange.network`, `indexer`, `websocket`
and `node` together when changing networks. `node` is a TLS gRPC host and port,
without an HTTP prefix. Subaccounts 0 through 127 are supported. `poll_seconds`
controls indexer polling. These bots do not use a v3 account WebSocket.
Configuration can instead be supplied as JSON5 in the `strategy` environment
variable. Strategy settings are bound to saved state; changing an active strategy
requires reconciling its existing orders first.

Optional notifications use `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
Telegram failures are logged without changing order execution.

## Run

```sh
cp .env.example .env
# Edit .env and data/strategy.json before starting.
docker compose build
docker compose up -d
docker compose logs -f
```

Compose mounts `./data` so state survives container replacement. Stop the process
before changing state. Stopping a bot leaves exchange orders in place; inspect and
cancel them through the exchange if needed. Only one process may use a data directory.
Use a separate directory and subaccount for each strategy.

For a local Python installation, install the native build tools required by
`coincurve` and the wallet dependencies, then use:

```sh
python3 -m venv .venv
. .venv/bin/activate
PIP_BUILD_CONSTRAINT="$PWD/build-constraints.txt" python3 -m pip install -r requirements-dev.txt
```

The dYdX SDK currently constrains some signing dependencies to older compatible
versions. `build-constraints.txt` supplies the build tools expected by coincurve 20;
Docker installs the native build prerequisites. Runtime dependency versions must
continue to satisfy `python3 -m pip check`.

## Recovery and order handling

`data/state.json` records strategy progress. `data/exchange.json` journals client
IDs **before** order submission. Keep both files together. An ambiguous timeout
is reconciled against its existing client ID; it never automatically becomes a
new trade. If an order remains unknown, execution stops for reconciliation.
Do not delete the journal to bypass an error.

Legacy v3 state is incompatible. Reconcile any previous orders and positions,
archive the old state, and start the Chain bot with a fresh data directory.
The exchange journal is bound to its wallet, network and subaccount.

Limit orders use Chain long-term orders with a default 24-hour expiry. Prices
are aligned to market ticks, and sizes must be exact multiples of `stepSize`.
Market orders use short-term IOC orders with a side-aware slippage bound.
A cancellation must be confirmed before a replacement is submitted.
Profit figures use actual fill prices and trading fees. They exclude funding,
network transaction fees and unrealised position value.

## Tests

```sh
docker build --target test -t bot-test .
docker run --rm --network none bot-test
```

The regression suite runs without exchange access or credentials. It exercises
strategy transitions, restart recovery, order identities, fills and cancellations.
SDK tests build real order protobuf messages and derive a public test wallet
locally. Passing these tests does not establish live execution or profitability.

Software is supplied as is under the repository licence.
