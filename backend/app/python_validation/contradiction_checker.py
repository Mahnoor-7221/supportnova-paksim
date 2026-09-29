from .common import ValidationCheck

_FIELD_ALIASES = {
    'category': ('issue_category', 'category'),
    'subcategory': ('subcategory',),
    'department': ('department',),
    'urgency': ('urgency',),
    'priority': ('priority',),
    'policy_id': ('policy_id',),
}


def _normalized(value):
    return ' '.join(str(value or '').casefold().split())


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {'true', 'yes', 'required'}
    return bool(value)


def validate(ctx):
    parsed = ctx.parsed or {}
    expected = ctx.expected or {}
    checks = []

    for field, aliases in _FIELD_ALIASES.items():
        expected_value = expected.get(field)
        if expected_value in (None, ''):
            continue
        actual = next((parsed[key] for key in aliases if parsed.get(key) not in (None, '')), '')
        if _normalized(actual) != _normalized(expected_value):
            checks.append(ValidationCheck(
                f'{field}_match', 'FAIL',
                f'Rule matrix expects {field}={expected_value!s}; GenAI returned {actual or "missing"!s}',
                {'expected': expected_value, 'actual': actual},
            ))

    if 'escalation' in expected:
        actual = parsed.get('escalation_required', parsed.get('escalation'))
        expected_value = _as_bool(expected['escalation'])
        if actual is None or _as_bool(actual) != expected_value:
            checks.append(ValidationCheck(
                'escalation_match', 'FAIL',
                f'Rule matrix expects escalation={expected_value}; GenAI returned '
                f'{_as_bool(actual) if actual is not None else "missing"}',
                {'expected': expected_value, 'actual': actual},
            ))

    return checks
