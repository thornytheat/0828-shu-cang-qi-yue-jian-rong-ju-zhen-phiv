import json


def artifact(run):
    packet = {
        'schema': 'review-evidence/1',
        'manifest': run['report']['manifest'],
        'balance': run['report']['balance'],
        'cases': run['report']['cases'],
        'intake': run['report']['intake'],
        'review': {key: run[key] for key in ('status', 'revision', 'note', 'reviewed')},
    }
    return (json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def adjusted_artifact(view):
    """交账批次的补证证据：原批次结果冻结可查，补证与重算结果单列。"""
    run = view['run']
    packet = {
        'schema': 'review-evidence/2',
        'manifest': run['report']['manifest'],
        'frozen': {
            'balance': run['report']['balance'],
            'intake': run['report']['intake'],
            'review': {key: run[key] for key in ('status', 'revision', 'note', 'reviewed')},
        },
        'targets': view['targets'],
        'supplements': view['supplements'],
        'adjustment': view['adjustment'],
    }
    return (json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
