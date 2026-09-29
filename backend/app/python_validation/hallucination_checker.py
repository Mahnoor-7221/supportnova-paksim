from .common import ValidationCheck

def validate(ctx):
    p=ctx.parsed or {}; out=[]
    pid=p.get('policy_id')
    if pid and ctx.policy_lookup and pid not in ctx.policy_lookup: out.append(ValidationCheck('policy_reference','FAIL',f'Policy reference {pid} is not present in the approved lookup',[pid]))
    response=p.get('professional_response','') or ''
    if not response: out.append(ValidationCheck('response','WARNING','No professional response was generated'))
    return out
