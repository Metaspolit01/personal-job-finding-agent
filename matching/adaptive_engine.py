import sqlite3
import logging
from config.settings import DB_PATH
from database.memory_manager import get_preferences

logger = logging.getLogger(__name__)

def calculate_adaptive_adjustment(job_title: str, job_company: str, job_desc: str) -> float:
    """
    Analyze past user interaction patterns (applications, ignores) in SQLite to calculate
    a dynamic adjustment score (bonus or penalty) for the current job listing.
    
    Rule-based adaptive learning:
    1. If company is in rejected_companies -> HUGE penalty (-100.0)
    2. If company was repeatedly ignored (>= 3 times) -> Company suppression (-20.0)
    3. If role/keywords (e.g. "UI/UX", "Kubernetes") were repeatedly ignored or applied:
       - Every apply to a keyword -> +5.0 bonus (max +20.0)
       - Every ignore of a keyword -> -5.0 penalty (max -20.0)
    """
    adjustment = 0.0
    title_lower = job_title.lower()
    desc_lower = job_desc.lower()
    company_lower = job_company.lower()
    
    # 1. Company checking
    prefs = get_preferences()
    rejected_companies = [c.lower() for c in prefs.get("rejected_companies", [])]
    
    # Check manual company blacklist
    for rc in rejected_companies:
        if rc in company_lower:
            logger.info(f"Adaptive Engine: Suppressing company '{job_company}' due to manual rejection list.")
            return -100.0
            
    # Connect to check interaction counts
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if the company has been repeatedly ignored
        cursor.execute("""
            SELECT COUNT(*) FROM ignored_jobs ij
            JOIN jobs_seen js ON ij.job_id = js.job_id
            WHERE LOWER(js.company) = ?
        """, (company_lower,))
        company_ignored_count = cursor.fetchone()[0]
        
        if company_ignored_count >= 3:
            logger.info(f"Adaptive Engine: Penalizing company '{job_company}' due to repeated ignores ({company_ignored_count} times).")
            adjustment -= 20.0
            
        # Check dynamic keywords (Roles & Technologies)
        # We look at terms: "kubernetes", "devops", "cloud", "ui/ux", "design", "fresher", "intern"
        target_keywords = ["kubernetes", "devops", "cloud", "ui/ux", "design", "terraform", "docker", "aws", "python"]
        
        for keyword in target_keywords:
            # Does the job contain this keyword?
            if keyword in title_lower or keyword in desc_lower:
                # Count how many times user applied to jobs containing this keyword
                cursor.execute("""
                    SELECT COUNT(*) FROM applied_jobs aj
                    JOIN jobs_seen js ON aj.job_id = js.job_id
                    WHERE LOWER(js.title) LIKE ? OR LOWER(js.description) LIKE ?
                """, (f"%{keyword}%", f"%{keyword}%"))
                applied_count = cursor.fetchone()[0]
                
                # Count how many times user ignored jobs containing this keyword
                cursor.execute("""
                    SELECT COUNT(*) FROM ignored_jobs ij
                    JOIN jobs_seen js ON ij.job_id = js.job_id
                    WHERE LOWER(js.title) LIKE ? OR LOWER(js.description) LIKE ?
                """, (f"%{keyword}%", f"%{keyword}%"))
                ignored_count = cursor.fetchone()[0]
                
                # Calculate keyword-specific bias
                keyword_bias = (applied_count * 5.0) - (ignored_count * 5.0)
                # Cap the individual keyword bias between -15.0 and +15.0
                keyword_bias = max(-15.0, min(15.0, keyword_bias))
                
                if keyword_bias != 0.0:
                    logger.debug(f"Adaptive Engine: Keyword '{keyword}' has bias {keyword_bias:.1f} (Applied: {applied_count}, Ignored: {ignored_count})")
                    adjustment += keyword_bias
                    
    except Exception as e:
        logger.error(f"Error calculating adaptive scoring adjustment: {e}")
    finally:
        conn.close()
        
    # Cap total scoring adjustment between -50.0 and +30.0
    adjustment = max(-50.0, min(30.0, adjustment))
    if adjustment != 0.0:
        logger.info(f"Adaptive Engine: Total adjustment for '{job_title}' at '{job_company}' is {adjustment:.1f}")
        
    return adjustment
