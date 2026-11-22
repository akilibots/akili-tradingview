import pytest
from run import create_app, JobQueue, Webhooks
from runtime import State


@pytest.fixture
def client(conf, fake, state_dir, monkeypatch):
    monkeypatch.setenv('WEBHOOK_SECRET', 'test-secret')
    monkeypatch.setenv('ALLOWED_IPS', '127.0.0.1')
    return create_app(conf, fake).test_client()


def payload(ref='t12', **extra):
    return {'secret': 'test-secret', 'ref': ref, 'reset': ['t13', 't14'], 'market': 'SOL-USD', 'side': 'buy', 'price': 16, 'size': 10, 'multiple': False, **extra}


def submit(client, data):
    response = client.post('/place', json=data)
    assert response.status_code == 202
    assert client.application.extensions['process_one']()
    return client.get('/jobs/' + str(response.json['id']), headers={'Authorization': 'Bearer test-secret'})


def test_example_duplicate_and_reset(client, fake):
    assert submit(client, payload('t13', reset=[])).json['status'] == 'done'
    assert submit(client, payload()).json['status'] == 'done'
    assert fake.orders['webhook:1']['status'] == 'CANCELED'
    assert submit(client, payload()).json['status'] == 'done'
    assert len(fake.calls) == 2
    result = client.post('/cancel', json={'secret': 'test-secret', 'orders': ['t12', 'missing']})
    assert result.status_code == 202
    assert client.application.extensions['process_one']()
    assert fake.orders['webhook:2']['status'] == 'CANCELED'


def test_authentication_and_source_ip(client, fake):
    assert client.post('/place', json=payload(secret='wrong')).status_code == 403
    assert client.post('/place', json=payload(), environ_base={'REMOTE_ADDR': '1.2.3.4'}).status_code == 403
    assert fake.calls == []


@pytest.mark.parametrize('extra', [{'size': -1}, {'side': 'oops'}, {'multiple': 'false'}, {'reset': 't12'}, {'till': 1672531200}, {'price': 'NaN'}])
def test_invalid_inputs_do_not_place_orders(client, fake, extra):
    assert client.post('/place', json=payload(**extra)).status_code == 400
    assert not fake.calls


def test_http_response_and_persisted_deduplication(client, fake, conf):
    assert submit(client, payload()).is_json
    restarted = create_app(conf, fake, State()).test_client()
    assert submit(restarted, payload()).json['status'] == 'done'
    assert len(fake.calls) == 1


def test_multiple_can_place_more_than_once(client, fake):
    submit(client, payload(multiple=True))
    submit(client, payload(multiple=True))
    assert len(fake.calls) == 2


def test_missing_secret_never_calls_exchange(client, fake, monkeypatch):
    monkeypatch.delenv('WEBHOOK_SECRET')
    assert client.post('/place', json=payload()).status_code == 503
    assert not fake.calls


def test_reset_cancels_all_orders_for_a_multiple_reference(client, fake):
    submit(client, payload('old', multiple=True))
    submit(client, payload('old', multiple=True))
    submit(client, payload('new', reset=['old']))
    assert fake.orders['webhook:1']['status'] == 'CANCELED'
    assert fake.orders['webhook:2']['status'] == 'CANCELED'


def test_acknowledgement_does_not_wait_for_exchange(client, fake):
    response = client.post('/place', json=payload())
    assert response.status_code == 202
    assert not fake.calls
    job = client.get('/jobs/' + str(response.json['id']), headers={'Authorization': 'Bearer test-secret'})
    assert job.json['status'] == 'queued'


def test_durable_job_replay_does_not_repeat_multiple_order(conf, fake, state_dir):
    service = Webhooks(conf, fake)
    data = payload(multiple=True)
    del data['secret']
    data['till'] = None
    service.state.data['sequence'] = 1
    service.state.data['pending'] = {'action': 'place', 'key': 'webhook:1', 'payload': data, 'job_id': '1'}
    service.state.save()
    fake.place('webhook:1', 'SOL-USD', 'BUY', 10, 16)
    recovered = Webhooks(conf, fake, State())
    recovered.place(data, job_id='1')
    recovered.place(data, job_id='1')
    assert len(fake.calls) == 1
    assert len(recovered.state.data['refs']['t12']) == 1


def test_failed_job_blocks_following_jobs(conf, fake, state_dir):
    queue = JobQueue()
    service = Webhooks(conf, fake)
    data = payload()
    del data['secret']
    data['till'] = None
    queue.submit('place', data)
    queue.submit('place', data)
    def failure(*args, **kwargs):
        raise TimeoutError('uncertain exchange result')
    fake.place = failure
    assert queue.process_one(lambda: service) is False
    assert queue.status(1)['status'] == 'failed'
    assert queue.process_one(lambda: service) is False
    assert queue.status(2)['status'] == 'queued'
