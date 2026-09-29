from .common import ValidationCheck
import re

PROHIBITED=["guarantee a refund","guaranteed refund","bypass verification","skip identity verification","disable security"]

def _normalize(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', (text or '').casefold())).strip()

def _detect_prohibited(text):
    normalized=_normalize(text)
    return [x for x in PROHIBITED if _normalize(x) in normalized]

def validate(ctx):
    parsed=ctx.parsed or {}
    parts=[parsed.get('professional_response',''),parsed.get('recommended_action','')]
    parts.extend(parsed.get('resolution_steps') or [])
    text=' '.join(str(part) for part in parts)
    found=_detect_prohibited(text)
    checks=[ValidationCheck('unsafe_response','FAIL',f'Unsafe instruction or promise: {phrase}',{'phrase':phrase}) for phrase in found]

    expected=ctx.expected or {}
    action_text=_normalize(text)
    for action in expected.get('required_actions') or []:
        normalized=_normalize(action)
        if normalized and normalized not in action_text:
            checks.append(ValidationCheck('required_action','FAIL',f'Required resolution action is missing: {action}',{'action':action}))
    for action in expected.get('prohibited_actions') or []:
        normalized=_normalize(action)
        if normalized and normalized in action_text:
            checks.append(ValidationCheck('prohibited_action','FAIL',f'Prohibited resolution action was recommended: {action}',{'action':action}))
    return checks
