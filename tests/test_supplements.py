"""交账后的补证流程：否认仍隔离、正确定义恢复采信、撤回退回隔离、分组重算。"""
import io

import pytest

from app.business import DomainIssue
from app.review.service import (adjustment_view, execute, review,
                                submit_supplement, withdraw_supplement)
from conftest import csv_data

CORRECT = {'field': '2', 'data_type': 1, 'scale': 0, 'nullable': 0, 'has_default': 0}


def restorable_bytes():
    # ERR3 恢复为 int32 生产者后，9999 组可通过。
    return csv_data([
        ['000101', '0001', 'producer', '1', '1', '0', '0', '0', '交接'],
        ['000102', '0001', 'reader', '1', '1', '0', '1', '0', '复核'],
        ['000103', '0001', 'gate', '0', '0', '0', '0', '0', '调整'],
        ['ERR3', '9999', 'producer', '2', '1', '0', '0', '0', '旧定义'],
        ['ERR3', '9999', 'producer', '2', '2', '0', '0', '0', '新定义'],
        ['E9001', '9999', 'reader', '2', '1', '0', '0', '0', '读取器'],
        ['E9002', '9999', 'gate', '0', '0', '0', '0', '0', '闸口'],
    ])


def close(store, data=None):
    run = execute(store, data or restorable_bytes())
    review(store, run['id'], dict(revision=0, status='CLOSED', note='到期先交账'))
    return run


def case(view, code):
    return next(item for item in view['adjustment']['cases'] if item['case'] == code)


def test_supplement_requires_closed_run(store):
    run = execute(store, restorable_bytes())
    with pytest.raises(DomainIssue, match='RUN_NOT_CLOSED'):
        submit_supplement(store, run['id'], dict(record='ERR3', action='DENY', note='否认一份'))


def test_deny_without_definition_keeps_record_isolated(store):
    run = close(store)
    view = submit_supplement(store, run['id'], dict(record='ERR3', action='DENY', note='只否认旧定义'))
    adjustment = view['adjustment']
    assert adjustment['summary'] == dict(restored=0, denied=1, open=0, withdrawn=0, conflicts=1)
    assert adjustment['balance']['releasable'] is False
    assert adjustment['supplements'][0]['state'] == 'DENIED'
    # 原批次报告保持冻结。
    assert store.load(run['id'])['report']['intake']['rejected'] == 2


def test_correct_definition_restores_and_recomputes_group(store):
    run = close(store)
    view = submit_supplement(store, run['id'],
                             dict(record='ERR3', action='CORRECT', definition=CORRECT, note='晚到补证正确定义'))
    adjustment = view['adjustment']
    assert adjustment['summary']['restored'] == 1
    assert case(view, '9999')['status'] == 'READY'
    assert case(view, '9999')['basis'] == 'ADJUSTED'
    assert adjustment['balance']['releasable'] is True
    # 两个冲突物理行收敛为一条逻辑采信行。
    assert adjustment['physical_input'] == 7
    assert adjustment['balance']['input'] == 6 and adjustment['balance']['isolated'] == 0


def test_unaffected_groups_keep_original_basis(store):
    run = close(store)
    view = submit_supplement(store, run['id'],
                             dict(record='ERR3', action='CORRECT', definition=CORRECT, note='晚到补证正确定义'))
    assert case(view, '0001')['status'] == 'READY' and case(view, '0001')['basis'] == 'ORIGINAL'


def test_withdraw_restored_supplement_returns_to_isolation(store):
    run = close(store)
    view = submit_supplement(store, run['id'],
                             dict(record='ERR3', action='CORRECT', definition=CORRECT, note='晚到补证正确定义'))
    supplement = view['supplements'][0]
    updated = withdraw_supplement(store, run['id'], supplement['id'], dict(revision=supplement['revision']))
    adjustment = updated['adjustment']
    assert adjustment['summary'] == dict(restored=0, denied=0, open=1, withdrawn=1, conflicts=1)
    assert case(updated, '9999')['status'] != 'READY'
    assert adjustment['balance']['releasable'] is False
    # 其他组照旧通过。
    assert case(updated, '0001')['status'] == 'READY'


def test_denied_supplement_cannot_be_withdrawn(store):
    run = close(store)
    view = submit_supplement(store, run['id'], dict(record='ERR3', action='DENY', note='只否认旧定义'))
    supplement = view['supplements'][0]
    with pytest.raises(DomainIssue, match='SUPPLEMENT_NOT_ADOPTED'):
        withdraw_supplement(store, run['id'], supplement['id'], dict(revision=supplement['revision']))


def test_only_one_active_supplement_per_record(store):
    run = close(store)
    submit_supplement(store, run['id'], dict(record='ERR3', action='DENY', note='先否认'))
    with pytest.raises(DomainIssue, match='SUPPLEMENT_EXISTS'):
        submit_supplement(store, run['id'],
                          dict(record='ERR3', action='CORRECT', definition=CORRECT, note='再给定义'))


def test_withdraw_allows_new_supplement_and_recompute(store):
    run = close(store)
    view = submit_supplement(store, run['id'],
                             dict(record='ERR3', action='CORRECT', definition=CORRECT, note='晚到补证正确定义'))
    supplement = view['supplements'][0]
    withdraw_supplement(store, run['id'], supplement['id'], dict(revision=supplement['revision']))
    again = submit_supplement(store, run['id'],
                              dict(record='ERR3', action='CORRECT', definition=CORRECT, note='重新补证'))
    assert again['adjustment']['balance']['releasable'] is True
    assert len(again['supplements']) == 2  # 历史补证仍留痕


def test_unknown_record_and_bad_action_are_rejected(store):
    run = close(store)
    with pytest.raises(DomainIssue, match='SUPPLEMENT_NOT_FOUND'):
        submit_supplement(store, run['id'], dict(record='NOPE', action='DENY', note='找不到记录'))
    with pytest.raises(DomainIssue, match='SUPPLEMENT_FIELDS'):
        submit_supplement(store, run['id'], dict(record='ERR3', action='HACK', note='非法动作'))


def test_correct_requires_valid_definition(store):
    run = close(store)
    bad = dict(CORRECT, scale=-1)  # 负数不被数字解析接受，结构校验即拒绝
    with pytest.raises(DomainIssue):
        submit_supplement(store, run['id'],
                          dict(record='ERR3', action='CORRECT', definition=bad, note='非法定义'))

    bad_type = dict(CORRECT)
    bad_type['data_type'] = 'oops'
    with pytest.raises(DomainIssue):
        submit_supplement(store, run['id'],
                          dict(record='ERR3', action='CORRECT', definition=bad_type, note='非法类型'))


def test_domain_invalid_definition_does_not_restore_eligibility(store):
    run = close(store)
    bad = dict(CORRECT, data_type=9)  # 结构层通过，字段注册阶段触发 INVALID_FIELD
    view = submit_supplement(store, run['id'],
                             dict(record='ERR3', action='CORRECT', definition=bad, note='领域非法'))
    # 记录按补证恢复入组，但重算判定失败，组不获得通过资格、批次仍不可放行。
    assert case(view, '9999')['status'] == 'INVALID_FIELD'
    assert view['adjustment']['balance']['releasable'] is False


def test_note_length_is_validated(store):
    run = close(store)
    with pytest.raises(DomainIssue, match='SUPPLEMENT_FIELDS'):
        submit_supplement(store, run['id'], dict(record='ERR3', action='DENY', note='短'))


def test_adjustment_view_is_repeatable_and_frozen(store):
    run = close(store)
    submit_supplement(store, run['id'],
                      dict(record='ERR3', action='CORRECT', definition=CORRECT, note='晚到补证正确定义'))
    first = adjustment_view(store, run['id'])
    second = adjustment_view(store, run['id'])
    assert first['adjustment'] == second['adjustment']
    frozen = store.load(run['id'])['report']
    assert frozen['balance']['releasable'] is False


def test_http_supplement_lifecycle_and_adjusted_evidence(client):
    response = client.post('/api/runs', data={'file': (io.BytesIO(restorable_bytes()), 'x.csv')})
    run_id = response.json['id']
    client.patch(f'/api/runs/{run_id}', json={'revision': 0, 'status': 'CLOSED', 'note': '到期先交账'})

    denied = client.post(f'/api/runs/{run_id}/supplements',
                         json={'record': 'ERR3', 'action': 'DENY', 'note': '只否认旧定义'})
    assert denied.status_code == 200 and denied.json['adjustment']['balance']['releasable'] is False

    loaded = client.get(f'/api/runs/{run_id}').json
    assert loaded['adjustment']['adjustment']['supplements'][0]['state'] == 'DENIED'

    evidence = client.get(f'/api/runs/{run_id}/adjustment/evidence').json
    assert evidence['schema'] == 'review-evidence/2'
    assert evidence['frozen']['intake']['rejected'] == 2
    assert evidence['adjustment']['summary']['denied'] == 1


def test_http_404_for_missing_supplement_target(client):
    response = client.post('/api/runs', data={'file': (io.BytesIO(restorable_bytes()), 'x.csv')})
    run_id = response.json['id']
    client.patch(f'/api/runs/{run_id}', json={'revision': 0, 'status': 'CLOSED', 'note': '到期先交账'})
    result = client.post(f'/api/runs/{run_id}/supplements',
                         json={'record': 'NOPE', 'action': 'DENY', 'note': '记录不存在'})
    assert result.status_code == 404 and result.json['code'] == 'SUPPLEMENT_NOT_FOUND'


def test_dirty_sample_conflicts_remain_deniable(store, dirty):
    run = execute(store, dirty)
    # 脏样例本身账平（每行都有着落），可以交账。
    assert run['report']['balance']['balanced']
    review(store, run['id'], dict(revision=0, status='CLOSED', note='脏样例到期交账'))
    view = submit_supplement(store, run['id'], dict(record='ERR3', action='DENY', note='否认重发前数据'))
    assert view['adjustment']['summary']['denied'] == 1
    assert view['adjustment']['balance']['releasable'] is False
