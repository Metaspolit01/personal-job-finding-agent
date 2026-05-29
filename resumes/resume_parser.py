import os
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

def load_resume_text(resume_dir="resumes") -> str:
    """Scan the resumes directory for PDF or TXT files, and extract text from the first one found."""
    # Ensure directory exists relative to project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(base_dir, resume_dir)
    
    if not os.path.exists(target_dir):
        logger.warning(f"Resume directory '{target_dir}' does not exist.")
        return ""
        
    files = [f for f in os.listdir(target_dir) if f.endswith(('.pdf', '.txt'))]
    if not files:
        logger.info(f"No resume files (.pdf or .txt) found in '{target_dir}'.")
        return ""
        
    resume_path = os.path.join(target_dir, files[0])
    logger.info(f"Loading resume from: {resume_path}")
    
    try:
        if resume_path.endswith('.txt'):
            with open(resume_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif resume_path.endswith('.pdf'):
            doc = fitz.open(resume_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
    except Exception as e:
        logger.error(f"Failed to read resume file at {resume_path}: {e}")
        
    return ""
