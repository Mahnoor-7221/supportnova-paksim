from .common import ValidationCheck

def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {'true', 'yes', 'required'}
    return bool(value)

def validate(ctx):
    exp=ctx.expected or {}; dec=ctx.escalation_decision or {}; p=ctx.parsed or {}
    expected=bool(dec.get('required',exp.get('escalation',False)))
    value=p.get('escalation_required',p.get('escalation'))
    actual=_as_bool(value) if value is not None else False
    if expected != actual:
        triggers=', '.join(dec.get('triggers') or exp.get('escalation_triggers') or [])
        detail=f'; deterministic triggers: {triggers}' if triggers else ''
        return [ValidationCheck('escalation','FAIL',f'Expected escalation={expected}, got {actual}{detail}',{'expected':expected,'actual':value,'triggers':dec.get('triggers',[])})]
    return []
