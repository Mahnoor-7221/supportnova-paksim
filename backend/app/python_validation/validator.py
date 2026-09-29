from .common import ValidationCheck
from . import hallucination_checker,resolution_validator,policy_validator,contradiction_checker,escalation_validator

def build_policy_lookup(db):
    from ..models import Policy
    result={}
    for p in db.query(Policy).filter(Policy.is_active.is_(True)).all():
        sections=[p.section] if p.section else []
        result[p.policy_id]={'version':p.version,'sections':sections,'title':p.title,
                             'document_id':p.document_id,'source_reference':p.policy_id}
    return result

def expected_from_rule(rule):
    if not rule: return {}
    return {'category':rule.category,'subcategory':rule.subcategory,'department':rule.department,
            'urgency':rule.urgency,'priority':rule.priority,'escalation':bool(rule.escalation),
            'escalation_reason':rule.escalation_reason,'escalation_department':rule.escalation_department,
            'rule_id':rule.rule_id,'policy_id':rule.policy_id,
            'required_actions':list(rule.required_actions or []),
            'prohibited_actions':list(rule.prohibited_actions or []),
            'follow_up':bool(rule.follow_up)}

def run_validation(db, complaint, analysis, created_by=None):
    from ..models import ValidationResult, ValidationCheck as DBCheck, ComplaintHistory, ManualReview
    from ..services.rule_matcher import extract_signals, match_rule
    from ..services.escalation_engine import evaluate_escalation
    rule,_,_=match_rule(db,complaint)
    expected=expected_from_rule(rule)
    parsed=analysis.parsed or {}
    from .common import ValidationContext
    import json
    policy_lookup=build_policy_lookup(db)
    policy_found=not expected.get('policy_id') or expected['policy_id'] in policy_lookup
    escalation_decision=evaluate_escalation(
        complaint,rule,extract_signals(complaint),
        injection_detected=complaint.injection_detected,
        policy_found=policy_found,
    )
    expected['rule_escalation']=bool(rule.escalation) if rule else False
    expected['escalation']=bool(escalation_decision['required'])
    expected['escalation_triggers']=list(escalation_decision['triggers'])
    expected['escalation_department']=escalation_decision['department'] or expected.get('escalation_department','')
    ctx=ValidationContext(complaint,parsed,expected,rule,escalation_decision,[],policy_lookup,complaint.injection_detected,analysis.is_valid_schema)
    checks=[]
    for mod in (hallucination_checker,resolution_validator,policy_validator,contradiction_checker,escalation_validator):
        checks.extend(mod.validate(ctx))
    if not analysis.is_valid_schema: checks.append(ValidationCheck('schema','FAIL','AI output failed schema validation'))
    if complaint.injection_detected: checks.append(ValidationCheck('injection','WARNING','Prompt injection indicators detected'))
    fails=sum(c.status=='FAIL' for c in checks); warns=sum(c.status=='WARNING' for c in checks)
    status='MISMATCH' if fails else ('VERIFIED_WITH_WARNING' if warns else 'VERIFIED')
    summary={'expected':expected,'checks':len(checks),'failures':fails,'warnings':warns}
    row=ValidationResult(complaint_id=complaint.id,analysis_id=analysis.id,status=status,summary=summary,created_by=created_by)
    db.add(row); db.flush()
    for c in checks: db.add(DBCheck(validation_result_id=row.id,check_name=c.name,expected=json.dumps(expected, default=str),actual=json.dumps(parsed, default=str),status=c.status,message=c.message))
    complaint.verification_status=status
    complaint.verified_category=expected.get('category',''); complaint.verified_department=expected.get('department',''); complaint.verified_urgency=expected.get('urgency',''); complaint.verified_priority=expected.get('priority',''); complaint.verified_escalation=bool(escalation_decision['required'])
    previous_status=complaint.status
    complaint.status='MANUAL_REVIEW' if fails else ('ESCALATED' if expected.get('escalation') else 'ANALYZED')
    if complaint.status != previous_status:
        db.add(ComplaintHistory(
            complaint_id=complaint.id,
            from_status=previous_status,
            to_status=complaint.status,
            note=f'Python validation completed with status {status}',
            actor_id=created_by,
        ))
    if fails:
        reasons='; '.join(c.message for c in checks if c.status=='FAIL')
        open_review=(db.query(ManualReview)
                     .filter(ManualReview.complaint_id==complaint.id,
                             ManualReview.source=='validation',
                             ManualReview.status=='OPEN').first())
        if open_review is None:
            db.add(ManualReview(complaint_id=complaint.id,reason=reasons[:2000],source='validation'))
    db.commit(); db.refresh(row)
    return row
