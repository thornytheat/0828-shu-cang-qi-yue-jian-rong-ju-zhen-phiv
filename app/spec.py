COLUMNS = ('field', 'data_type', 'scale', 'nullable', 'has_default')
KINDS = ('producer', 'reader', 'gate')
PROJECT = {'name': '数仓契约兼容矩阵', 'actor': '数据平台发版工程师', 'stages': [('intake', '样例采信'), ('prepare', '字段注册'), ('calculate', '读写匹配'), ('policy', '兼容签收'), ('balance', '运行对账')], 'chart': '字段兼容', 'mark': '数'}
