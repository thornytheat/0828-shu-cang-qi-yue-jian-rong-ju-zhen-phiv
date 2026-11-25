"""补证登记与撤回的并发安全。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.business import DomainIssue
from app.review.service import execute, review, submit_supplement, withdraw_supplement
from tests.test_supplements import CORRECT, restorable_bytes


def close(store):
    run = execute(store, restorable_bytes())
    review(store, run['id'], dict(revision=0, status='CLOSED', note='到期先交账'))
    return run


def test_parallel_deny_has_single_winner(store):
    run = close(store)
    barrier = Barrier(4)

    def attempt(_):
        barrier.wait(3)
        try:
            submit_supplement(store, run['id'], dict(record='ERR3', action='DENY', note='并发否认补证'))
            return 'OK'
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count('OK') == 1
    assert results.count('SUPPLEMENT_EXISTS') == 3
    assert len(store.supplements(run['id'])) == 1


def test_parallel_withdraw_has_one_winner(store):
    run = close(store)
    view = submit_supplement(store, run['id'],
                             dict(record='ERR3', action='CORRECT', definition=CORRECT, note='正确补证'))
    supplement = view['supplements'][0]
    barrier = Barrier(2)

    def attempt(_):
        barrier.wait(3)
        try:
            withdraw_supplement(store, run['id'], supplement['id'],
                                dict(revision=supplement['revision']))
            return 'OK'
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == ['OK', 'STALE_REVIEW']
    refreshed = next(item for item in store.supplements(run['id']) if item['id'] == supplement['id'])
    assert refreshed['status'] == 'WITHDRAWN' and refreshed['revision'] == supplement['revision'] + 1
