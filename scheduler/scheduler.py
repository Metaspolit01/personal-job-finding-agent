import logging
from database.db_manager import init_db, get_unsent_top_jobs, mark_as_sent, save_job, is_duplicate
from notifications.telegram_sender import send_jobs_to_telegram
from scraper.scraper import scrape_linkedin_jobs
from filtering.filter import is_filtered_out
from matching.scorer import calculate_final_score
from resumes.resume_parser import load_resume_text
import time

logger = logging.getLogger(__name__)

def run_job_search(chat_id: str = None):
    logger.info("Initializing Database...")
    init_db()
    
    logger.info("Loading active resume...")
    resume_text = load_resume_text()
    if not resume_text.strip():
        logger.warning("No active resume found in resumes/. Cannot perform job matching.")
        if chat_id:
            from config.settings import BOT_TOKEN
            import requests
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": chat_id,
                "text": "⚠️ *No active resume found!*\n\nPlease upload a resume (.pdf or .txt) to the bot first, and then try again.",
                "parse_mode": "Markdown"
            })
        return False
        
    logger.info("Starting Scraping process...")
    keywords = ["DevOps Intern", "Junior DevOps", "Cloud Intern", "Kubernetes Intern", "UI/UX Design Intern"]
    scraped = scrape_linkedin_jobs(keywords, location="India", max_jobs=25)
    
    logger.info(f"Scraped {len(scraped)} jobs. Filtering and scoring...")
    
    new_jobs_saved = 0
    for job in scraped:
        job_id = job["job_id"]
        
        # 1. Skip if already processed in database
        if is_duplicate(job_id):
            continue
            
        # 2. Skip if matches blacklist filters
        if is_filtered_out(job["title"], job["company"], job["description"]):
            continue
            
        # 3. Calculate hybrid match score
        logger.info(f"Evaluating job '{job['title']}' at '{job['company']}'...")
        score = calculate_final_score(
            job["description"],
            resume_text,
            job_title=job["title"],
            job_company=job["company"],
            job_id=job["job_id"]
        )
        
        # 4. Save to database
        save_job(job, score)
        new_jobs_saved += 1
        logger.info(f"Saved job '{job['title']}' with score {score:.2f}")
        
    logger.info(f"Pipeline complete. Saved {new_jobs_saved} new matching jobs.")
    
    # Send daily notification if conditions are met
    return notify_top_jobs(chat_id=chat_id)

def notify_top_jobs(chat_id: str = None):
    logger.info("Fetching top 10 unsent jobs for Telegram delivery...")
    top_jobs = get_unsent_top_jobs(limit=10)
    
    if top_jobs:
        logger.info(f"Sending {len(top_jobs)} new jobs to Telegram.")
        success = send_jobs_to_telegram(top_jobs, chat_id=chat_id)
        if success:
            job_ids = [j['job_id'] for j in top_jobs]
            mark_as_sent(job_ids)
            logger.info("Successfully sent and marked jobs as sent.")
            return True
    else:
        logger.info("No new matching jobs to send right now.")
        
    return False
