AREA_LABELS = (
    "course_registration",
    "calendar_conflicts",
    "degree_requirements",
    "academic_standing",
    "academic_calendar",
    "exam_schedules",
    "grading",
    "transcripts",
    "course_substitution",
    "proctoring",
)

SMALLTALK = "smalltalk"
OUT_OF_SCOPE = "out_of_scope"

ALL_ROUTES = AREA_LABELS + (SMALLTALK, OUT_OF_SCOPE)

AREAS_WITH_DOCS = frozenset({"grading", "transcripts"})

LABEL_DESCRIPTIONS = {
    "course_registration": "course registration eligibility",
    "calendar_conflicts": "schedule conflict detection",
    "degree_requirements": "degree requirements and progress",
    "academic_standing": "academic standing and GPA",
    "academic_calendar": "academic calendar and events",
    "exam_schedules": "exam schedules and exam rules",
    "grading": "grading system and grade explanations",
    "transcripts": "transcript eligibility and requests",
    "course_substitution": "course substitutions and waivers",
    "proctoring": "exam proctoring information",
    "smalltalk": "greetings and casual conversation",
    "out_of_scope": "questions outside university affairs",
}
