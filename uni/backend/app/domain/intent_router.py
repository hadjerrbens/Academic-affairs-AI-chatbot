# backend/app/domain/intent_router.py
import re

def keyword_label(text: str) -> str:
    """
    Fallback router. Returns the feature_area label based on keywords.
    """
    text = text.lower()
    
    # 1. Course Substitution / Waiver
    if re.search(r'\b(waiver|substitute|substitution|exempt)\b', text):
        return "course_substitution"
        
    # 2. Proctoring
    if re.search(r'\b(proctor|proctored|proctoring|id|identification)\b', text):
        return "proctoring"
        
    # 3. Transcripts
    if re.search(r'\b(transcript|official record|unofficial record)\b', text):
        return "transcripts"
        
    # 4. Grading
    if re.search(r'\b(grade|grading|gpa|a-|b\+|points|scale)\b', text):
        return "grading"
        
    # 5. Exams
    if re.search(r'\b(exam|final|midterm|test|clash|schedule)\b', text):
        return "exam_schedules"
        
    # 6. Calendar
    if re.search(r'\b(calendar|holiday|semester|deadline|term|start|end)\b', text):
        return "academic_calendar"
        
    # 7. Standing
    if re.search(r'\b(standing|probation|warning|dismissal|appeal)\b', text):
        return "academic_standing"
        
    # 8. Degree Requirements
    if re.search(r'\b(degree|major|requirement|audit|progress|graduate)\b', text):
        return "degree_requirements"
        
    # 9. Conflicts
    if re.search(r'\b(overlap|conflict|back-to-back|tight)\b', text):
        return "calendar_conflicts"
        
    # 10. Registration
    if re.search(r'\b(register|enroll|drop|seat|capacity|prereq)\b', text):
        return "course_registration"
        
    # 11. Smalltalk
    if re.search(r'\b(hi|hello|hey|good morning|good afternoon)\b', text):
        return "smalltalk"
        
    return "out_of_scope"

# Helper for the agent loop
def get_tools_for_label(label: str) -> list[str]:
    mapping = {
        "course_substitution": ["explain_waiver_process", "check_waiver_eligibility"],
        "proctoring": ["get_proctoring_info"],
        # ... M1, M2, M3, M4 tools would be mapped here too
    }
    return mapping.get(label, [])

def keyword_route(text: str) -> dict:
    """Shape ChatService expects: {"primary": label, "secondary": None}."""
    return {"primary": keyword_label(text), "secondary": None}
