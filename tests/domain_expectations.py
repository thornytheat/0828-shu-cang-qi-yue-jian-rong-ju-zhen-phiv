EXPECTED = {'0001': (3, 0, 'READY'),
 '0002': (2, 0, 'READY'),
 '0003': (0, None, 'FIELD_REGISTRY_CONFLICT'),
 '0004': (2, 2, 'BREAKING_SCHEMA')}
EVIDENCE = {'0001': {'compatible': {'1': 'WIDEN_INTEGER',
                         '2': 'WIDEN_SCALE',
                         '3': 'DEFAULT'},
          'violations': {}},
 '0004': {'compatible': {},
          'violations': {'1': ['DECIMAL_SCALE_NARROWED',
                               'NULLABILITY_NARROWED'],
                         '2': ['MISSING_REQUIRED']}}}
