"""Authenticated TradingView webhooks for dYdX Chain."""
import hmac
import os
import re
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
import threading
import time

from flask import Flask, abort, jsonify, request
from waitress import serve

from exchange import Exchange
from runtime import State, load_config, log, number, single_instance

DEFAULT_IPS = ['52.89.214.238', '34.212.75.30', '54.218.53.128', '52.32.178.7']


def identifiers(values):
    if not isinstance(values, list) or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', v) for v in values):
        raise ValueError('Order references must be a list of short alphanumeric identifiers')
    return values


def validate_place(payload):
    identifiers([payload['ref']])
    identifiers(payload['reset'])
    if payload['ref'] in payload['reset']:
        raise ValueError('An order cannot reset its own reference')
    if payload['side'] not in {'buy', 'sell'} or type(payload['multiple']) is not bool or number(payload['size']) <= 0 or number(payload['price']) <= 0:
        raise ValueError('Invalid order side, size, price or multiple flag')
    if not isinstance(payload['market'], str) or not re.fullmatch(r'[A-Z0-9]+-USD', payload['market']):
        raise ValueError('Invalid dYdX market')
    if payload['till'] is not None and (type(payload['till']) is not int or not time.time() + 60 <= payload['till'] <= time.time() + 95 * 86400):
        raise ValueError('till must be a future Unix timestamp')


class Webhooks:
    def __init__(self, conf, exchange, state=None):
        self.conf, self.exchange = conf, exchange
        self.state = state or State(initial={'refs': {}, 'sequence': 0, 'pending': None, 'completed': {}})

    def apply_pending(self):
        d = self.state.data
        pending = d['pending']
        if pending is None:
            return None
        payload = pending['payload']
        for ref in payload['reset'] if pending['action'] == 'place' else payload['orders']:
            if ref in d['refs']:
                for order in d['refs'][ref]:
                    self.exchange.cancel(order)
                del d['refs'][ref]
                self.state.save()
        result = {'cancelled': payload['orders']} if pending['action'] == 'cancel' else None
        if pending['action'] == 'place':
            ref = self.exchange.place(pending['key'], payload['market'], payload['side'].upper(), payload['size'], payload['price'], till=payload['till'])
            d['refs'].setdefault(payload['ref'], []).append(ref)
            result = ref
        if pending['job_id'] is not None:
            d['completed'][pending['job_id']] = result
        d['pending'] = None
        self.state.save()
        return result

    def place(self, payload, job_id=None):
        validate_place(payload)
        if job_id is not None and job_id in self.state.data['completed']:
            return self.state.data['completed'][job_id], 200
        self.apply_pending()
        d = self.state.data
        if job_id is not None and job_id in d['completed']:
            return d['completed'][job_id], 200
        if payload['ref'] in d['refs'] and not payload['multiple']:
            result = d['refs'][payload['ref']][-1]
            if job_id is not None:
                d['completed'][job_id] = result
                self.state.save()
            return result, 200
        # Each accepted request gets a durable identity before touching the exchange.
        d['sequence'] += 1
        d['pending'] = {'action': 'place', 'key': f'webhook:{d["sequence"]}', 'payload': payload, 'job_id': job_id}
        self.state.save()
        return self.apply_pending(), 201

    def cancel(self, payload, job_id=None):
        identifiers(payload['orders'])
        if job_id is not None and job_id in self.state.data['completed']:
            return self.state.data['completed'][job_id]
        self.apply_pending()
        if job_id is not None and job_id in self.state.data['completed']:
            return self.state.data['completed'][job_id]
        self.state.data['pending'] = {'action': 'cancel', 'payload': payload, 'job_id': job_id}
        self.state.save()
        return self.apply_pending()


class JobQueue:
    def __init__(self, path='data/jobs.sqlite3'):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, action TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, result TEXT)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=2)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def submit(self, action, payload):
        with self.connect() as db:
            cursor = db.execute("INSERT INTO jobs(action,payload,status) VALUES(?,?,'queued')", (action, json.dumps(payload)))
            return cursor.lastrowid

    def status(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT status,result FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            return None
        return {'id': job_id, 'status': row[0], 'result': json.loads(row[1]) if row[1] is not None else None}

    def process_one(self, service):
        with self.connect() as db:
            row = db.execute("SELECT id,action,payload,status FROM jobs WHERE status != 'done' ORDER BY id LIMIT 1").fetchone()
            if row is None or row[3] == 'failed':
                return False
            db.execute("UPDATE jobs SET status='processing' WHERE id=?", (row[0],))
        job_id, action, raw, _ = row
        try:
            handler = service()
            if action == 'place':
                result, _ = handler.place(json.loads(raw), job_id=str(job_id))
            else:
                result = handler.cancel(json.loads(raw), job_id=str(job_id))
        except Exception as error:
            # Persist the failure and stop the queue at this job for reconciliation.
            with self.connect() as db:
                db.execute("UPDATE jobs SET status='failed', result=? WHERE id=?", (json.dumps({'error': str(error)}), job_id))
            log(f'Webhook job {job_id} failed; inspect its saved result', 'TradingView')
            return False
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='done', result=? WHERE id=?", (json.dumps(result), job_id))
        log(f'Webhook job {job_id} completed', 'TradingView')
        return True


def create_app(conf=None, exchange=None, state=None, queue=None):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 16384
    lock = threading.Lock()
    service = None
    jobs = queue

    def get_queue():
        nonlocal jobs
        with lock:
            if jobs is None:
                jobs = JobQueue()
        return jobs

    @app.before_request
    def authenticate():
        secret = os.environ.get('WEBHOOK_SECRET', '')
        if not secret:
            abort(503)
        payload = request.get_json(silent=True)
        supplied = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if isinstance(payload, dict):
            supplied = supplied or payload.get('secret', '')
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, secret):
            abort(403)
        allowed = os.environ.get('ALLOWED_IPS', ','.join(DEFAULT_IPS)).split(',')
        if '*' not in allowed and request.remote_addr not in allowed:
            abort(403)

    def get_service():
        nonlocal service
        if service is None:
            settings = conf if conf is not None else load_config()
            service = Webhooks(settings, exchange if exchange is not None else Exchange(settings['exchange']), state)
        return service

    app.extensions['process_one'] = lambda: get_queue().process_one(get_service)

    @app.route('/place', methods=['POST'])
    def place():
        data = request.get_json()
        try:
            payload = {key: data[key] for key in ('ref', 'market', 'side', 'size', 'price', 'multiple')}
            payload['reset'] = data.get('reset', [])
            payload['till'] = data.get('till')
            validate_place(payload)
            job_id = get_queue().submit('place', payload)
            return jsonify(id=job_id, status='queued'), 202
        except (KeyError, ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400

    @app.route('/cancel', methods=['POST'])
    def cancel():
        try:
            payload = {'orders': request.get_json()['orders']}
            identifiers(payload['orders'])
            job_id = get_queue().submit('cancel', payload)
            return jsonify(id=job_id, status='queued'), 202
        except (KeyError, ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400

    @app.route('/jobs/<int:job_id>', methods=['GET'])
    def job_status(job_id):
        result = get_queue().status(job_id)
        if result is None:
            abort(404)
        return jsonify(result)

    return app


app = create_app()

if __name__ == '__main__':
    if not os.environ.get('WEBHOOK_SECRET'):
        raise ValueError('Set WEBHOOK_SECRET before starting the webhook server')
    def work():
        while True:
            app.extensions['process_one']()
            time.sleep(0.1)
    with single_instance():
        threading.Thread(target=work, daemon=True).start()
        serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), threads=4)
