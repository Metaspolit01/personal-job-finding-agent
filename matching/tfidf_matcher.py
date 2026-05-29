from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging

logger = logging.getLogger(__name__)

def calculate_tfidf_similarity(job_desc: str, resume_text: str) -> float:
    """Calculate the cosine similarity between the job description and the resume using TF-IDF."""
    if not job_desc.strip() or not resume_text.strip():
        return 0.0
        
    try:
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf = vectorizer.fit_transform([resume_text, job_desc])
        similarity = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        return float(similarity)
    except Exception as e:
        logger.error(f"Error calculating TF-IDF similarity: {e}")
        return 0.0
