from collections import Counter

from app.business import DomainIssue
from app.intake.reader import records
from app.intake.resolve import conflicts_of, partition
from app.intake.schema import HEADER, record


def parse_candidates(data):
    """读取一份来源，返回通过结构校验的候选行与隔离明细，供采信与补证重算共用。"""
    counted = repeated = blanks = 0
    candidates, rejected = [], []
    try:
        for line, values in records(data):
            counted += 1
            if not any(v.strip() for v in values):
                blanks += 1
                continue
            if tuple(values) == HEADER:
                repeated += 1
                continue
            try:
                candidates.append((line, record(values)))
            except DomainIssue as error:
                key = values[0][:36] if values else ''
                case = values[1][:36] if len(values) > 1 else ''
                rejected.append(dict(line=line, record=key, case=case, reason=error.code))
    except DomainIssue:
        raise
    except Exception as error:
        from csv import Error
        if isinstance(error, Error):
            raise DomainIssue('CSV_MALFORMED') from error
        raise
    return dict(input=counted, repeated=repeated, blank=blanks,
                candidates=candidates, rejected=rejected)


def inspect(data):
    parsed = parse_candidates(data)
    accepted, conflicts = partition(parsed['candidates'])
    rejects = sorted(parsed['rejected'] + conflicts, key=lambda row: row['line'])
    return dict(input=parsed['input'], accepted=len(accepted), repeated=parsed['repeated'],
                blank=parsed['blank'], rejected=len(rejects),
                reasons=dict(Counter(r['reason'] for r in rejects)),
                isolation=rejects, rows=accepted)


def conflict_keys(candidates):
    """只保留同一记录号出现两份及以上不一致字段定义的记录键。"""
    return conflicts_of(candidates).keys()
