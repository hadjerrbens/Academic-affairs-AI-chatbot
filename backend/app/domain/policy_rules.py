# backend/app/domain/policy_rules.py
from app.core.prolog_engine import ask, KBError

def evaluate_substitution(target: str, substitute: str, student_courses: list) -> dict:
    # 1. Validation
    if target.upper() == substitute.upper():
        raise ValueError("Target course and substitute course cannot be the same.")

    # 2. Format data for Prolog (Initialize the list here!)
    taken_list = []
    for c in student_courses:
        is_dict = isinstance(c, dict)
        status = c.get("status", "completed") if is_dict else getattr(c, "status", "completed")
        
        if status == "completed":
            course_code = c["course_code"] if is_dict else c.course_code
            grade_points = c["grade_points"] if is_dict else c.grade_points
            credits = c["credits"] if is_dict else c.credits
            
            taken_list.append(("taken", course_code, grade_points, credits))

    # 3. Call Prolog
    try:
        rows = ask(
            "sub_verdict(Target, Substitute, Taken, Verdict, Reason)",
            target=target.upper(),
            substitute=substitute.upper(),
            taken=taken_list
        )
    except KBError:
        return {"verdict": "error", "reasons": ["System error connecting to rules engine."], "required_documents": []}

    # 4. Parse result
    if not rows:
        return {"verdict": "needs_advisor_review", "reasons": ["No clear rule found."], "required_documents": []}

    result = rows[0]
    verdict = result.get("Verdict", "needs_advisor_review")
    reason = result.get("Reason", "")

    # 5. Get required docs
    required_docs = []
    if verdict != "needs_advisor_review":
        doc_rows = ask("sub_rule(Target, _, _, _, _, Docs)", target=target.upper())
        if doc_rows:
            required_docs = doc_rows[0].get("Docs", [])

    return {
        "verdict": verdict,
        "reasons": [reason],
        "required_documents": required_docs
    }

def get_proctoring_policy(mode: str) -> dict:
    try:
        rows = ask("proc_policy(Mode, Provider, Location, IdReq, TechReq, Reschedule)", mode=mode)
    except KBError:
        return {"error": "KB_ERROR", "message": "Could not load proctoring policy."}

    if not rows:
        return {"error": "NOT_FOUND", "message": f"No policy found for mode: {mode}"}

    r = rows[0]
    return {
        "mode": r.get("Mode"),
        "provider": r.get("Provider"),
        "location": r.get("Location"),
        "id_requirements": r.get("IdReq"),
        "technical_requirements": r.get("TechReq"),
        "reschedule_policy": r.get("Reschedule")
    }