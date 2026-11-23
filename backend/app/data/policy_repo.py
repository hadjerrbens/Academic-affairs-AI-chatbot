# backend/app/data/policy_repo.py
import csv
import os

# In a real production app, this might query Mongo or a DB.
# For the MVP, we read the CSVs directly to validate inputs.
DATA_DIR = os.path.join(os.path.dirname(__file__), "../../../data/seed")

def get_substitution_rules() -> dict:
    """Reads substitution_rules.csv into a dictionary for quick lookups."""
    rules = {}
    filepath = os.path.join(DATA_DIR, "substitution_rules.csv")
    
    if not os.path.exists(filepath):
        return rules
        
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rules[row['target_course']] = row
            
    return rules

def get_proctoring_policies() -> dict:
    """Reads proctoring_policies.csv into a dictionary."""
    policies = {}
    filepath = os.path.join(DATA_DIR, "proctoring_policies.csv")
    
    if not os.path.exists(filepath):
        return policies
        
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            policies[row['mode']] = row
            
    return policies

def validate_course_codes(target: str, substitute: str) -> bool:
    """
    Optional helper for the service layer to ensure the courses exist
    before hitting the Prolog engine.
    """
    rules = get_substitution_rules()
    # If the target isn't in the rules, maybe it just has no rule (which is fine)
    # but if the course code doesn't exist at all, we might want to catch it.
    # For now, just return True to let Prolog handle it.
    return True