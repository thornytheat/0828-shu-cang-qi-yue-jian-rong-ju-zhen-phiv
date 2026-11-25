from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic

from app.adjustment.service import build, conflict_targets, corrected_row, validate_definition
from app.business import DomainIssue
from app.config import RULE_VERSION
from app.modules.pipeline import run

FINALIZED = ('APPROVED', 'CLOSED')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def execute(store, data):
    start = monotonic()
    fingerprint = sha256(data).hexdigest()
    run_id = sha256(f'{RULE_VERSION}:{fingerprint}'.encode()).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != 'RUN_NOT_FOUND':
            raise
    report = run(data)
    report['manifest'] = dict(sha256=fingerprint, version=RULE_VERSION, created=now(),
                              duration_ms=round((monotonic()-start)*1000,3), bytes=len(data), run_id=run_id)
    return store.register(run_id, report, source=data)


def review(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue('REVIEW_FIELDS')
    revision, status, note = (values.get(key) for key in ('revision', 'status', 'note'))
    if type(revision) is not int or revision < 0 or status not in ('APPROVED', 'HELD', 'CLOSED') \
            or not isinstance(note, str) or not (3 <= len(note.strip()) <= 200):
        raise DomainIssue('REVIEW_FIELDS')
    current = store.load(run_id)
    if revision != current['revision']:
        raise DomainIssue('STALE_REVIEW')
    if current['status'] in FINALIZED:
        raise DomainIssue('RUN_FINALIZED')
    checks = current['report']['balance']
    if status == 'APPROVED' and not checks['releasable']:
        raise DomainIssue('UNRESOLVED_ISSUES')
    # 交账要求账平（每行都有着落），但允许保留隔离的待核记录。
    if status == 'CLOSED' and not checks['balanced']:
        raise DomainIssue('BATCH_NOT_BALANCED')
    return store.revise(run_id, revision, status, note.strip(), now())


def _closed_run(store, run_id):
    batch = store.load(run_id)
    if batch['status'] != 'CLOSED':
        raise DomainIssue('RUN_NOT_CLOSED')
    source = store.source(run_id)
    if source is None:
        raise DomainIssue('SOURCE_UNAVAILABLE')
    return batch, source


def submit_supplement(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue('SUPPLEMENT_FIELDS')
    _, source = _closed_run(store, run_id)
    key, action, note = values.get('record'), values.get('action'), values.get('note')
    if not isinstance(key, str) or not isinstance(note, str) or not (3 <= len(note.strip()) <= 200):
        raise DomainIssue('SUPPLEMENT_FIELDS')
    targets = {item['record']: item for item in conflict_targets(source)}
    target = targets.get(key)
    if target is None:
        raise DomainIssue('SUPPLEMENT_NOT_FOUND')
    if action == 'DENY':
        definition = None
    elif action == 'CORRECT':
        definition = validate_definition(values.get('definition'))
        # 走与来源文件相同的结构校验，非法字段定义不允许恢复采信。
        corrected_row([(target['lines'][0], target['copies'][0])], definition)
    else:
        raise DomainIssue('SUPPLEMENT_FIELDS')
    store.add_supplement(run_id, key, action, definition, note.strip(), now())
    return adjustment_view(store, run_id)


def withdraw_supplement(store, run_id, supplement_id, values):
    if not isinstance(values, dict) or type(values.get('revision')) is not int:
        raise DomainIssue('SUPPLEMENT_FIELDS')
    _closed_run(store, run_id)
    store.withdraw_supplement(supplement_id, run_id, values['revision'], now())
    return adjustment_view(store, run_id)


def adjustment_view(store, run_id):
    batch, source = _closed_run(store, run_id)
    supplements = store.supplements(run_id)
    adjusted = build(source, supplements)
    return dict(run=batch, targets=conflict_targets(source),
                supplements=supplements, adjustment=adjusted)
