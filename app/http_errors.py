from flask import jsonify

LABELS = {
    'FILE_TOO_LARGE':'文件超过 256 KiB', 'FILE_EMPTY':'文件没有内容', 'FILE_BLANK':'文件只有空白',
    'HEADER_ONLY':'文件只有标题行', 'HEADER_MISMATCH':'列名与字段字典不一致', 'ENCODING_INVALID':'请使用 UTF-8 CSV',
    'CSV_MALFORMED':'CSV 引号或行格式异常', 'ROW_LIMIT':'文件超过 2000 行', 'FILE_REQUIRED':'请选择 CSV 文件',
    'RUN_NOT_FOUND':'批次不存在', 'REVIEW_FIELDS':'请填写 3 至 200 字复核意见', 'STALE_REVIEW':'批次已更新，请刷新',
    'RUN_FINALIZED':'批次已签发', 'UNRESOLVED_ISSUES':'存在待处理差异', 'SAMPLE_UNKNOWN':'样例不存在', 'STAGE_UNKNOWN':'处理阶段不存在',
    'BATCH_NOT_BALANCED':'对账未平衡，不能交账', 'RUN_NOT_CLOSED':'批次尚未交账，不能登记补证',
    'SOURCE_UNAVAILABLE':'原批次来源未留存，无法重算', 'SUPPLEMENT_FIELDS':'补证字段不完整或定义非法',
    'SUPPLEMENT_EXISTS':'该记录已有生效补证，请先撤回', 'SUPPLEMENT_NOT_FOUND':'补证或冲突记录不存在',
    'SUPPLEMENT_TARGET_GONE':'原冲突已不存在，补证无法登记', 'SUPPLEMENT_NOT_ADOPTED':'否认型补证未恢复采信，不能撤回资格',
}
NOT_FOUND = {'RUN_NOT_FOUND', 'SAMPLE_UNKNOWN', 'STAGE_UNKNOWN', 'SUPPLEMENT_NOT_FOUND'}
CONFLICT = {'STALE_REVIEW', 'RUN_FINALIZED', 'UNRESOLVED_ISSUES', 'BATCH_NOT_BALANCED',
            'RUN_NOT_CLOSED', 'SUPPLEMENT_EXISTS', 'SUPPLEMENT_TARGET_GONE', 'SUPPLEMENT_NOT_ADOPTED'}


def response(error):
    code = error.code
    status = 404 if code in NOT_FOUND else 409 if code in CONFLICT else 413 if code == 'FILE_TOO_LARGE' else 422
    return jsonify(code=code, message=LABELS.get(code, code)), status
