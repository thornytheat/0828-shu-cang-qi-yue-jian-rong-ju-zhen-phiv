"""交账（CLOSED）规则：账平即可交，允许保留隔离待核记录。"""
import io

import pytest

from app.business import DomainIssue
from app.review.service import execute, review
from conftest import csv_data


def balanced_conflict_bytes():
    # 0001 组完整可通过；ERR3 同号两份冲突定义，整体账平但不可签发。
    return csv_data([
        ['000101', '0001', 'producer', '1', '1', '0', '0', '0', '交接'],
        ['000102', '0001', 'reader', '1', '1', '0', '1', '0', '复核'],
        ['000103', '0001', 'gate', '0', '0', '0', '0', '0', '调整'],
        ['ERR3', '9999', 'reader', '2', '1', '0', '0', '0', '旧定义'],
        ['ERR3', '9999', 'reader', '2', '2', '0', '0', '0', '新定义'],
    ])


def closed_run(store):
    run = execute(store, balanced_conflict_bytes())
    review(store, run['id'], dict(revision=0, status='CLOSED', note='到期先交账'))
    return run


def test_balanced_batch_with_isolation_can_close(store):
    run = execute(store, balanced_conflict_bytes())
    checks = run['report']['balance']
    assert checks['balanced'] and not checks['releasable'] and checks['isolated'] == 2
    closed = review(store, run['id'], dict(revision=0, status='CLOSED', note='到期先交账'))
    assert closed['status'] == 'CLOSED' and closed['revision'] == 1


def test_close_requires_balanced_books(store):
    import json
    run = execute(store, balanced_conflict_bytes())
    run['report']['balance']['balanced'] = False
    with store.connect() as db:
        db.execute('UPDATE runs SET report=? WHERE id=?',
                   (json.dumps(run['report'], ensure_ascii=False), run['id']))
    with pytest.raises(DomainIssue, match='BATCH_NOT_BALANCED'):
        review(store, run['id'], dict(revision=0, status='CLOSED', note='强行交账'))


def test_closed_batch_is_final(store):
    run = closed_run(store)
    with pytest.raises(DomainIssue, match='RUN_FINALIZED'):
        review(store, run['id'], dict(revision=1, status='HELD', note='交账后改动'))


def test_close_uses_optimistic_revision(store):
    run = execute(store, balanced_conflict_bytes())
    review(store, run['id'], dict(revision=0, status='HELD', note='先暂缓等待'))
    with pytest.raises(DomainIssue, match='STALE_REVIEW'):
        review(store, run['id'], dict(revision=0, status='CLOSED', note='旧版本交账'))


def test_close_note_kept_and_listed(store):
    run = execute(store, balanced_conflict_bytes())
    review(store, run['id'], dict(revision=0, status='CLOSED', note='  交账备注留存  '))
    item = next(row for row in store.list() if row['id'] == run['id'])
    assert item['status'] == 'CLOSED' and store.load(run['id'])['note'] == '交账备注留存'


def test_http_close_and_evidence_remains_frozen(client):
    response = client.post('/api/runs', data={'file': (io.BytesIO(balanced_conflict_bytes()), 'x.csv')})
    run_id = response.json['id']
    patched = client.patch(f'/api/runs/{run_id}',
                           json={'revision': 0, 'status': 'CLOSED', 'note': '到期先交账'})
    assert patched.status_code == 200 and patched.json['status'] == 'CLOSED'
    evidence = client.get(f'/api/runs/{run_id}/evidence').json
    assert evidence['schema'] == 'review-evidence/1' and evidence['intake']['rejected'] == 2
    assert evidence['review']['status'] == 'CLOSED'
