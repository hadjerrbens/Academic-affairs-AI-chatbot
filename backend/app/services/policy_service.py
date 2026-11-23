# backend/app/services/policy_service.py

# --- COMMENT THIS OUT UNTIL M4 BUILDS IT ---
# from app.core.tools import register_tool, ToolContext 

from app.domain.policy_rules import evaluate_substitution, get_proctoring_policy
from app.core.retrieval import retrieve_with_context
from pydantic import BaseModel
from typing import Optional

class ExplainWaiverArgs(BaseModel):
    pass


# @register_tool(feature_area="course_substitution", requires_auth=False)
async def explain_waiver_process(ctx=None, args=None) -> dict:
    # 1. Get the context from YOUR RAG layer
    context, citations = await retrieve_with_context("How to request a waiver or substitution", "course_substitution")
    
    # 2. Extract steps from the markdown (looking for numbered lists or bullet points)
    steps = []
    for line in context.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("1. ") or line.startswith("2. "):
            steps.append(line.lstrip("- 1234567890. ").strip())
            
    # Fallback if the doc doesn't have bullet points
    if not steps:
        steps = ["Speak to your department advisor.", "Provide official transcript.", "Provide signed substitution form."]
    
    summary = "To request a waiver or substitution, you must speak with your department advisor. You will need to provide your official transcript and a signed substitution form."
    
    return {
        "steps": steps,
        "summary": summary,
        "citations": citations
    }
class CheckWaiverArgs(BaseModel):
    target_course: str
    substitute_course: str

# @register_tool(feature_area="course_substitution", requires_auth=True)
async def check_waiver_eligibility(ctx, args: CheckWaiverArgs) -> dict:
    # Mocking student record until M2's DB is fully wired
    class MockStudent:
        completed = [{"course_code": "BUS202", "grade_points": 3.7, "credits": 3, "status": "completed"}]
    
    student = MockStudent() 

    try:
        result = evaluate_substitution(args.target_course, args.substitute_course, student.completed)
    except ValueError as e:
        return {"error": "VALIDATION_ERROR", "message": str(e)}

    verdict = result["verdict"]
    reason = result["reasons"][0] if result["reasons"] else ""
    summary = f"Verdict: {verdict}. {reason}"
    
    if result["required_documents"]:
        summary += f" Need: {', '.join(result['required_documents'])}."

    return {
        "verdict": verdict,
        "reasons": result["reasons"],
        "required_documents": result["required_documents"],
        "summary": summary
    }

class ProctoringArgs(BaseModel):
    exam_type: Optional[str] = None
    course_code: Optional[str] = None

# @register_tool(feature_area="proctoring", requires_auth=False)
async def get_proctoring_info(ctx=None, args: ProctoringArgs = None) -> dict:
    mode = args.exam_type
    if not mode and args.course_code:
        mode = "in_person" 

    if not mode:
        return {"error": "MISSING_ARG", "message": "Provide exam type or course code."}

    policy = get_proctoring_policy(mode.lower().replace("-", "_"))
    if "error" in policy:
        return policy

    summary = f"This exam uses {mode} proctoring. ID requirements: {policy['id_requirements']}"
    return {**policy, "summary": summary}