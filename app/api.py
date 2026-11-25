from flask import Blueprint, Response, current_app, jsonify, request

from app.business import DomainIssue
from app.evidence.render import adjusted_artifact, artifact
from app.inputs import read_input
from app.modules.pipeline import run
from app.review.service import (adjustment_view, execute, review,
                                submit_supplement, withdraw_supplement)

api = Blueprint('api', __name__, url_prefix='/api')
STAGES = {'intake': 1, 'prepare': 2, 'calculate': 3, 'policy': 4, 'balance': 5}


@api.post('/stages/<stage>')
def preview(stage):
    if stage not in STAGES:
        raise DomainIssue('STAGE_UNKNOWN')
    return jsonify(run(read_input(), STAGES[stage]))


@api.route('/runs', methods=['GET', 'POST'])
def runs():
    store = current_app.extensions['runs']
    if request.method == 'GET':
        return jsonify(items=store.list())
    return jsonify(execute(store, read_input()))


@api.route('/runs/<run_id>', methods=['GET', 'PATCH'])
def batch(run_id):
    store = current_app.extensions['runs']
    if request.method == 'GET':
        result = store.load(run_id)
        if result['status'] == 'CLOSED' and store.source(run_id) is not None:
            result['adjustment'] = adjustment_view(store, run_id)
        return jsonify(result)
    return jsonify(review(store, run_id, request.get_json(silent=True)))


@api.get('/runs/<run_id>/evidence')
def export(run_id):
    store = current_app.extensions['runs']
    report = store.load(run_id)
    body = artifact(report)
    return Response(body, mimetype='application/json', headers={
        'Content-Disposition': f'attachment; filename="review-{report["id"][:12]}.json"',
        'Cache-Control': 'no-store',
    })


@api.get('/runs/<run_id>/adjustment')
def adjustment(run_id):
    return jsonify(adjustment_view(current_app.extensions['runs'], run_id))


@api.post('/runs/<run_id>/supplements')
def add_supplement(run_id):
    return jsonify(submit_supplement(current_app.extensions['runs'], run_id,
                                     request.get_json(silent=True)))


@api.post('/runs/<run_id>/supplements/<int:supplement_id>/withdraw')
def remove_supplement(run_id, supplement_id):
    return jsonify(withdraw_supplement(current_app.extensions['runs'], run_id,
                                       supplement_id, request.get_json(silent=True)))


@api.get('/runs/<run_id>/adjustment/evidence')
def export_adjusted(run_id):
    view = adjustment_view(current_app.extensions['runs'], run_id)
    return Response(adjusted_artifact(view), mimetype='application/json', headers={
        'Content-Disposition': f'attachment; filename="adjustment-{run_id[:12]}.json"',
        'Cache-Control': 'no-store',
    })
