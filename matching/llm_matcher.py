import json
import logging
from matching.llm_orchestrator import query_ollama_securely

logger = logging.getLogger(__name__)

def evaluate_job_with_llm(job_description: str, resume_text: str) -> float:
    """
    Use local LLM (Qwen2.5 / Ollama) via secure orchestrator to semantically score the job vs resume.
    Returns a score out of 100.
    """
    prompt = (
        "Evaluate the following Job Description against the Resume and provide a match score from 0 to 100.\n"
        "Consider skills, required experience (must be junior/fresher), and remote/hybrid criteria.\n"
        "Respond ONLY with a JSON object containing a 'score' key (integer).\n\n"
        f"Resume:\n{resume_text}\n\n"
        f"Job Description:\n{job_description}\n"
    )
    
    try:
        response_text = query_ollama_securely(prompt, json_format=True)
        result_json = json.loads(response_text)
        score = float(result_json.get("score", 0.0))
        return score
    except Exception as e:
        logger.error(f"LLM match evaluation failed: {e}")
        return 0.0
