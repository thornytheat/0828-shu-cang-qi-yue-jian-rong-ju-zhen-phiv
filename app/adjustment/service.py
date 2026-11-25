"""交账后的补证重算。

规则：
- 补证只否认一份定义（DENY）而未给正确定义时，该记录仍计为隔离。
- 晚到补证给出正确定义（CORRECT）后，该记录恢复采信，受影响的业务组重算。
- 已采信的补证被撤回（WITHDRAWN）后，该记录退回隔离，受影响组失去通过资格，其他组照旧。
- 原批次的已交结果保持冻结，只在调整视图里反映补证后的对账。
"""
from app.business import DomainIssue
from app.intake.resolve import conflicts_of, partition
from app.intake.schema import HEADER, record
from app.intake.service import parse_candidates
from app.modules.grouping import case_groups
from app.modules.pipeline import evaluate
from app.modules.reconcile import balance

DEFINITION_FIELDS = ('field', 'data_type', 'scale', 'nullable', 'has_default')


def corrected_row(conflict, definition):
    """用补证给出的字段定义构造一条规范记录，保留原记录键、业务组与 kind。"""
    template = conflict[0][1]
    values = [template['record'], template['case'], template['kind'],
              *(str(definition[column]) for column in DEFINITION_FIELDS), template['note']]
    return record(values)


def build(source, supplements):
    """根据原始来源与补证列表，生成补证后的对账视图（不修改原报告）。"""
    parsed = parse_candidates(source)
    conflicts = conflicts_of(parsed['candidates'])
    active = {item['record_key']: item for item in supplements if item['status'] == 'ACTIVE'}
    withdrawn = {item['record_key'] for item in supplements if item['status'] == 'WITHDRAWN'}

    unknown = sorted((set(active) | set(withdrawn)) - set(conflicts))
    if unknown:
        raise DomainIssue('SUPPLEMENT_TARGET_GONE')

    restored = {}
    denied, open_keys = [], []
    views, affected_cases = [], set()
    for key, items in sorted(conflicts.items()):
        case = items[0][1]['case']
        if any(row['case'] != case for _, row in items):
            raise DomainIssue('SUPPLEMENT_FIELDS')
        entry = {'record': key, 'case': case,
                 'lines': [line for line, _ in items], 'state': 'OPEN'}
        current = active.get(key)
        if current is None:
            open_keys.append(key)
        elif current['action'] == 'DENY':
            denied.append(key)
            entry.update(state='DENIED', action='DENY', note=current['note'],
                         supplement_id=current['id'], revision=current['revision'])
        else:
            restored[key] = corrected_row(items, current['definition'])
            affected_cases.add(case)
            entry.update(state='RESTORED', action='CORRECT', note=current['note'],
                         supplement_id=current['id'], revision=current['revision'])
        if key in withdrawn:
            entry['state'] = 'WITHDRAWN'
            affected_cases.add(case)
        views.append(entry)

    # 原批次采信的行（去重回放后）保持不动；补证恢复的行并入后整组重算。
    accepted_rows = []
    seen = set()
    for _, row in sorted(parsed['candidates'], key=lambda pair: pair[0]):
        if row['record'] in conflicts or row['record'] in seen:
            continue
        seen.add(row['record'])
        accepted_rows.append(row)
    combined = [*accepted_rows, *restored.values()]
    cases = [evaluate(rows, 5) for _, rows in case_groups(combined)]
    for case in cases:
        if case['case'] in affected_cases:
            case['basis'] = 'ADJUSTED'
        else:
            case['basis'] = 'ORIGINAL'

    # 恢复一条冲突记录会把 k 个冲突物理行收敛为 1 条逻辑采信行。
    rejected_rows = [row for row in _all_rejected(parsed) if row['record'] not in restored]
    collapsed = sum(len(conflicts[key]) - 1 for key in restored)
    virtual = dict(
        input=parsed['input'] - collapsed,
        accepted=len(accepted_rows) + len(restored),
        rejected=len(rejected_rows),
        blank=parsed['blank'], repeated=parsed['repeated'],
    )
    adjusted = balance(virtual, cases)

    return dict(
        supplements=views,
        summary=dict(restored=len(restored), denied=len(denied),
                     open=len(open_keys), withdrawn=len(withdrawn),
                     conflicts=len(conflicts)),
        cases=cases,
        balance=adjusted,
        physical_input=parsed['input'],
        frozen_isolated=len(_all_rejected(parsed)),
    )


def _all_rejected(parsed):
    _, replay_rejected = partition(parsed['candidates'])
    return [*parsed['rejected'], *replay_rejected]


def conflict_targets(source):
    """列出可补证的冲突记录，供工作台展示。"""
    parsed = parse_candidates(source)
    return [{'record': key, 'case': items[0][1]['case'],
             'lines': [line for line, _ in items],
             'copies': [{column: row[column] for column in HEADER} for _, row in items]}
            for key, items in sorted(conflicts_of(parsed['candidates']).items())]


def validate_definition(values):
    """校验 CORRECT 补证自带的字段定义，返回归一化后的五个整数列。"""
    if not isinstance(values, dict):
        raise DomainIssue('SUPPLEMENT_FIELDS')
    try:
        return {column: values[column] for column in DEFINITION_FIELDS}
    except KeyError as error:
        raise DomainIssue('SUPPLEMENT_FIELDS') from error
