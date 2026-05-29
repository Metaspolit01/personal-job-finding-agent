from matching.llm_matcher import evaluate_job_with_llm
from matching.tfidf_matcher import calculate_tfidf_similarity
from matching.adaptive_engine import calculate_adaptive_adjustment
from database.memory_manager import save_scoring_run
import logging

logger = logging.getLogger(__name__)

def calculate_final_score(job_desc: str, resume_text: str, job_title: str = "", job_company: str = "", job_id: str = "") -> float:
    """
    Hybrid scoring: TF-IDF (50%) + Local LLM (40%) + Adaptive Learning Adjustment
    Clips final score to be strictly within [0, 100].
    Logs detailed breakdown to scoring_history.
    """
    # 1. TF-IDF Cosine Similarity (max 100)
    tfidf_score = calculate_tfidf_similarity(job_desc, resume_text) * 100
    
    # 2. Local LLM evaluation score (max 100)
    llm_score = evaluate_job_with_llm(job_desc, resume_text)
    
    # 3. Adaptive Learning bias based on interaction memory
    adaptive_bonus = 0.0
    if job_title or job_company:
        adaptive_bonus = calculate_adaptive_adjustment(job_title, job_company, job_desc)
        
    # Hybrid Score combination
    final_score = (tfidf_score * 0.5) + (llm_score * 0.4) + adaptive_bonus
    final_score = max(0.0, min(100.0, final_score))
    
    # Save scoring details to history for audit and transparency
    if job_id:
        save_scoring_run(
            job_id=job_id,
            tfidf_score=round(tfidf_score, 2),
            llm_score=round(llm_score, 2),
            adaptive_bonus=round(adaptive_bonus, 2),
            final_score=round(final_score, 2),
            resume_version="active_resume"
        )
        logger.info(
            f"Job '{job_title}' final score: {final_score:.2f} "
            f"(TF-IDF: {tfidf_score:.1f}, LLM: {llm_score:.1f}, Adaptive: {adaptive_bonus:.1f})"
        )
        
    return final_score
