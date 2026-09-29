from __future__ import annotations
from dataclasses import dataclass
import re
@dataclass
class ValidationContext:
    complaint: object; parsed: dict; expected: dict; matched_rule: object; escalation_decision: dict; chunks: list; policy_lookup: dict; injection_detected: bool; schema_valid: bool
@dataclass
class ValidationCheck:
    name: str; status: str; message: str; data: object = None

def overlap_ratio(a: str, b: str) -> float:
    A=set(re.findall(r"[a-z0-9]+",(a or '').lower())); B=set(re.findall(r"[a-z0-9]+",(b or '').lower()))
    return len(A&B)/max(1,len(A|B))
