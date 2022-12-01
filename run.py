from flask import Flask, request, abort
from dydx3 import Client
from dydx3.constants import *
from dydx3.helpers.request_helpers import generate_now_iso

from config import config

app = Flask(__name__)

ALLOWED_IPS = [
    # Allow only TradingView webhook IPs
    # https://www.tradingview.com/support/solutions/43000529348-about-webhooks/
    '52.89.214.238',
    '34.212.75.30',
    '54.218.53.128',
    '52.32.178.7',

    # Remove comment below to allow IP for development
    #'127.0.0.1',
]

GOOD_TILL = 1672531200


@app.before_request
def limit_remote_addr():
    client_ip = str(request.remote_addr)
    if client_ip not in ALLOWED_IPS:
        abort(403)


@app.route('/place', methods = ['POST',])
def place():
    data = request.json
    conf = config()

    xchange = Client(
        network_id=NETWORK_ID_MAINNET,
        host=API_HOST_MAINNET,
        api_key_credentials={
            'key': conf['dydx']['APIkey'],
            'secret': conf['dydx']['APIsecret'],
            'passphrase': conf['dydx']['APIpassphrase'],
        },
        stark_private_key=conf['dydx']['stark_private_key'],
        default_ethereum_address=conf['dydx']['default_ethereum_address'],
    )

    xchange.private.sign(
        request_path='/ws/accounts',
        method='GET',
        iso_timestamp=generate_now_iso(),
        data={},
    )

    account = xchange.private.get_account().data['account']

    if 'till' not in data:
        data['till'] = GOOD_TILL

    if data['side'] == 'buy':
        aSide = ORDER_SIDE_BUY

    if data['side'] == 'sell':
        aSide = ORDER_SIDE_SELL

    order = xchange.private.create_order(
        position_id=account['positionId'],
        market=data['market'],
        side=aSide,
        order_type=ORDER_TYPE_LIMIT,
        post_only=False,
        size=str(data['size']),
        price=str(data['price']),
        limit_fee='0.1',
        expiration_epoch_seconds=data['till'],
    ).data['order']

    return order


@app.route('/cancel', methods = ['POST',])
def cancel():
    data = request.json
    conf = config()

    xchange = Client(
        network_id=NETWORK_ID_MAINNET,
        host=API_HOST_MAINNET,
        api_key_credentials={
            'key': conf['dydx']['APIkey'],
            'secret': conf['dydx']['APIsecret'],
            'passphrase': conf['dydx']['APIpassphrase'],
        },
        stark_private_key=conf['dydx']['stark_private_key'],
        default_ethereum_address=conf['dydx']['default_ethereum_address'],
    )

    order = xchange.private.cancel_order(data['id']).data['order']

    return order


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=443, ssl_context='adhoc', debug=True)
