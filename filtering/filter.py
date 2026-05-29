import logging

logger = logging.getLogger(__name__)

# List of keywords indicating recruitment agencies, staffing firms, consultancies, or training institutes
COMPANY_BLACKLIST = [
    "consultancy", "consulting", "staffing", "recruitment", "recruiting", "hr services",
    "placement", "manpower", "career transition", "search group", "talent acquisition",
    "training institute", "academy", "classes", "global services", "solutions pvt"
]

# List of keywords indicating non-entry-level or non-matching jobs
ROLE_BLACKLIST = [
    "senior", "sr.", "sr ", "lead", "principal", "architect", "manager", "director",
    "head of", "vp", "president", "chief"
]

def is_filtered_out(title: str, company: str, description: str) -> bool:
    """
    Check if a job listing should be filtered out based on company, role blacklist, or memory rejections.
    Returns True if the job should be skipped (filtered out), and False otherwise.
    """
    title_lower = title.lower()
    company_lower = company.lower()
    
    # 1. Filter out by company blacklist from persistent memory
    try:
        from database.memory_manager import get_preferences
        prefs = get_preferences()
        rejected_companies = [c.lower() for c in prefs.get("rejected_companies", [])]
        for term in rejected_companies:
            if term in company_lower:
                logger.info(f"Filtered out job '{title}' because company '{company}' matched memory rejected company '{term}'.")
                return True
    except Exception as e:
        logger.error(f"Error fetching memory rejected companies: {e}")
    
    # 2. Filter out by static company blacklist
    for term in COMPANY_BLACKLIST:
        if term in company_lower:
            logger.info(f"Filtered out job '{title}' because company '{company}' matched blacklist term '{term}'.")
            return True
            
    # 3. Filter out senior roles from the title
    for term in ROLE_BLACKLIST:
        if term in title_lower:
            logger.info(f"Filtered out job '{title}' because title matched blacklist term '{term}'.")
            return True
            
    return False
