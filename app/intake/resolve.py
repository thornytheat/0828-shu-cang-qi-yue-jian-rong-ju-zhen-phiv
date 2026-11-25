from collections import defaultdict


def grouped(candidates):
    by_key = defaultdict(list)
    for line, row in candidates:
        by_key[row['record']].append((line, row))
    return by_key


def conflicts_of(candidates):
    """返回 {记录键: [(行号, 行), ...]}，仅含字段定义互相冲突的记录。"""
    return {key: items for key, items in grouped(candidates).items()
            if any(row != items[0][1] for _, row in items)}


def partition(candidates):
    by_key = grouped(candidates)
    accepted, rejected = [], []
    for key, records in by_key.items():
        first = records[0][1]
        if any(row != first for _, row in records):
            rejected.extend({'line': line, 'record': key, 'case': row['case'], 'reason': 'DUPLICATE_CONFLICT'} for line,row in records)
            continue
        accepted.append(first)
        rejected.extend({'line': line, 'record': key, 'case': row['case'], 'reason': 'DUPLICATE_REPLAY'} for line,row in records[1:])
    return accepted, rejected
