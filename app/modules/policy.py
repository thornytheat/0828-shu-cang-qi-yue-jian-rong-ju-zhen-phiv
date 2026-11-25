from app.business import decision


def policy(result):
    return decision(result,'BREAKING_SCHEMA' if result['value'] else None)
