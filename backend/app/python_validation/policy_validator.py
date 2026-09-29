from .common import ValidationCheck
import re
def find_policy_ids(text): return re.findall(r'\b[A-Z]{2,8}-POL-\d{2,4}\b', text or '')
def validate(ctx):
    p=ctx.parsed or {}; exp=ctx.expected or {}; out=[]
    expected_id=exp.get('policy_id') or ''
    actual_id=p.get('policy_id') or ''
    if expected_id and actual_id != expected_id:
        out.append(ValidationCheck('policy_match','FAIL',f"Expected policy {expected_id} but received {actual_id or 'missing'}"))

    cited_ids=set(find_policy_ids(' '.join([
        str(actual_id), str(p.get('policy_section') or ''), str(p.get('professional_response') or ''),
    ])))
    if actual_id:
        cited_ids.add(actual_id)
    lookup=ctx.policy_lookup or {}
    for policy_id in sorted(cited_ids):
        policy=lookup.get(policy_id)
        if policy is None:
            out.append(ValidationCheck('policy_reference','FAIL',f'Policy {policy_id} is not an active approved policy',{'policy_id':policy_id}))
            continue
        version=p.get('policy_version') or ''
        if version and version != policy.get('version'):
            out.append(ValidationCheck('policy_version','FAIL',f"Policy {policy_id} version {version} is not current; expected {policy.get('version')}"))
        section=p.get('policy_section') or ''
        sections=policy.get('sections') or []
        if section and sections and section not in sections:
            out.append(ValidationCheck('policy_section','FAIL',f"Section {section} is not registered for policy {policy_id}"))
    return out
