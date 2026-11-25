from app.business import measured


def compute(data):
    registry, readers = data
    compatible, violations = {}, {}
    for field in readers:
        dtype, scale, nullable, default = registry['reader',field]
        producer = registry.get(('producer',field))
        reasons = []
        status = 'EXACT'
        if not producer:
            if default or nullable:
                status = 'DEFAULT' if default else 'IMPLICIT_NULL'
            else:
                reasons.append('MISSING_REQUIRED')
        else:
            written, digits, maybe_null, _ = producer
            if written != dtype:
                if (written,dtype)==(1,2):
                    status = 'WIDEN_INTEGER'
                else:
                    reasons.append('TYPE_CHANGED')
            elif dtype == 4:
                if digits > scale:
                    reasons.append('DECIMAL_SCALE_NARROWED')
                elif digits < scale:
                    status = 'WIDEN_SCALE'
            if maybe_null and not nullable:
                reasons.append('NULLABILITY_NARROWED')
        if reasons:
            violations[str(field)] = reasons
        else:
            compatible[str(field)] = status
    return measured(len(violations),0,'处',{'compatible':compatible,'violations':violations})
