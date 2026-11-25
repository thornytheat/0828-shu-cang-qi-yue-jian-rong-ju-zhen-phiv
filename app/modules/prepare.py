from app.business import DomainIssue, by_kind, prepared, single


def prepare(rows):
    single(rows,'gate')
    registry = {}
    reader_fields = by_kind(rows,'reader')
    if not reader_fields:
        raise DomainIssue('READER_EMPTY')
    for row in rows:
        side, field, dtype, scale, null, default = (row[k] for k in ('kind','field','data_type','scale','nullable','has_default'))
        if side == 'gate':
            continue
        if not field or dtype not in (1,2,3,4) or not 0 <= scale <= 18 or (dtype != 4 and scale) or null > 1 or default > 1:
            raise DomainIssue('INVALID_FIELD')
        if (side,field) in registry:
            raise DomainIssue('FIELD_REGISTRY_CONFLICT')
        registry[side,field] = (dtype,scale,null,default)
    return prepared(len(reader_fields),{'producers':len(registry)-len(reader_fields),'readers':len(reader_fields)},(registry,sorted(r['field'] for r in reader_fields)))
