import json

import pytest
import requests

from app.test_hosted_asset_reference_service import FakeRepository, Response, SequencedHttp
from app.services.hosted_asset_reference_service import HostedAssetReferenceService, HostedAssetReferenceError


def evidence(caplog):
    return [json.loads(r.message.split('hosted_reference_verification ', 1)[1])
            for r in caplog.records if r.message.startswith('hosted_reference_verification ')]


def test_edit_source_attempts_are_correlated_and_secret_free(caplog):
    http = SequencedHttp(gets=[Response(416, headers={'Content-Type': 'text/html', 'Content-Range': 'bytes */10'}),
                              requests.exceptions.SSLError('https://user:secret@host/path?token=secret'),
                              requests.Timeout('secret')])
    service = HostedAssetReferenceService(repository=FakeRepository(), http_client=http, sleep=lambda _: None)
    with pytest.raises(HostedAssetReferenceError, match='Hosted edit source could not be verified after 3 attempts'):
        service.verify('https://user:secret@cdn.test/private-secret?token=secret',
                       asset_id='EDIT_SOURCE', request_id='generation_request_test')
    rows = evidence(caplog)
    assert len(rows) == 3
    assert [r['category'] for r in rows] == ['http', 'tls', 'timeout']
    assert rows[0]['http_status'] == 416
    assert rows[0]['content_range'] == 'bytes */10'
    assert all(r['request_id'] == 'generation_request_test' and r['reference_role'] == 'EDIT_SOURCE' for r in rows)
    assert 'secret' not in caplog.text
    assert [r['retry'] for r in rows] == [True, True, False]


@pytest.mark.parametrize('status', [401, 403, 404])
def test_permanent_status_has_one_diagnostic(status, caplog):
    service = HostedAssetReferenceService(repository=FakeRepository(), http_client=SequencedHttp(gets=[Response(status)]))
    with pytest.raises(HostedAssetReferenceError, match='canonical reference verification returned HTTP'):
        service.verify('https://cdn.test/image', asset_id=7)
    assert len(evidence(caplog)) == 1
    assert evidence(caplog)[0]['classification'] == 'permanent'


def test_success_records_redirects_and_closes_stream(caplog):
    response = Response(206, headers={'Content-Type': 'image/png', 'Content-Length': '1', 'Content-Range': 'bytes 0-0/42'})
    response.url = 'https://final.test/private?signature=secret'
    response.history = [object()]
    closed = []
    response.close = lambda: closed.append(True)
    service = HostedAssetReferenceService(repository=FakeRepository(), http_client=SequencedHttp(gets=[response]))
    service.verify('https://cdn.test/image', asset_id=7)
    row = evidence(caplog)[0]
    assert row['final_host'] == 'final.test' and row['redirect_count'] == 1
    assert row['classification'] == 'success' and closed == [True]
    assert 'signature' not in caplog.text and 'secret' not in caplog.text
