from playwright.sync_api import sync_playwright
import urllib.parse
import logging
import time
import sqlite3
from config.settings import DB_PATH
from monitoring.metrics_collector import (
    jobs_scraped_total,
    scraper_failures_total
)

logger = logging.getLogger(__name__)

def scrape_linkedin_jobs(keywords: list, location: str = "India", max_jobs: int = 15) -> list:
    """
    Scrape jobs from LinkedIn using Playwright and the public guest seeMoreJobPostings endpoint.
    It returns a list of dictionaries with job details.
    """
    scraped_jobs = []
    
    try:
        with sync_playwright() as p:
            # Launch headless browser
            try:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
            except Exception as e:
                scraper_failures_total.inc()
                logger.error(f"Playwright browser initialization crash: {e}")
                raise e
            
            # Iterate over multiple keywords (e.g. DevOps, Cloud, UI/UX)
            for keyword in keywords:
                logger.info(f"Scraping LinkedIn jobs for keyword: '{keyword}' in location: '{location}'")
                
                # Format parameters
                keyword_encoded = urllib.parse.quote(keyword)
                location_encoded = urllib.parse.quote(location)
                
                # Use LinkedIn's public guest endpoint which loads job cards cleanly as HTML
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword_encoded}&location={location_encoded}&start=0"
                
                try:
                    page.goto(url, timeout=15000)
                    
                    # Check if we got any job cards
                    cards = page.locator("li").all()
                    logger.info(f"Found {len(cards)} raw job cards for keyword '{keyword}'.")
                    
                    count = 0
                    for card in cards:
                        if len(scraped_jobs) >= max_jobs:
                            break
                        if count >= 10:  # limit per keyword to keep it fast
                            break
                            
                        title_el = card.locator(".base-search-card__title")
                        company_el = card.locator(".base-search-card__subtitle")
                        link_el = card.locator(".base-card__full-link")
                        
                        if title_el.count() > 0 and company_el.count() > 0 and link_el.count() > 0:
                            title = title_el.inner_text().strip()
                            company = company_el.inner_text().strip()
                            job_url = link_el.get_attribute("href").strip()
                            
                            # Clean tracking parameters from URL
                            clean_url = job_url.split("?")[0]
                            
                            # Generate unique job ID
                            job_id_raw = clean_url.split("-")[-1] or clean_url.split("/")[-1]
                            # Keep only digits or clean name
                            job_id = f"linkedin_{job_id_raw}"
                            
                            # Now navigate to individual page to extract full description
                            description = ""
                            try:
                                desc_page = context.new_page()
                                desc_page.goto(clean_url, timeout=10000)
                                
                                # LinkedIn guest description selector
                                desc_el = desc_page.locator(".show-more-less-html__markup, .description__text")
                                if desc_el.count() > 0:
                                    description = desc_el.first.inner_text().strip()
                                else:
                                    # Fallback description
                                    description = f"{title} position at {company} in {location}."
                                desc_page.close()
                            except Exception as e:
                                logger.warning(f"Could not load description for job {job_id}: {e}")
                                description = f"{title} position at {company} in {location}."
                                
                            # Add job
                            scraped_jobs.append({
                                "job_id": job_id,
                                "title": title,
                                "company": company,
                                "url": clean_url,
                                "source": "LinkedIn",
                                "description": description
                            })
                            
                            count += 1
                            jobs_scraped_total.inc()
                            logger.info(f"Extracted job: '{title}' at '{company}'")
                            
                            # Small delay to mimic human behavior
                            time.sleep(1)
                            
                except Exception as e:
                    scraper_failures_total.inc()
                    logger.error(f"Error while scraping keyword '{keyword}': {e}")
                    
            browser.close()
            
    except Exception as e:
        scraper_failures_total.inc()
        logger.error(f"Scraper execution crash: {e}")
        # Log to workflow_failures SQLite table
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO workflow_failures (workflow_name, failure_reason)
                VALUES ('scrape_linkedin_jobs', ?)
            """, (str(e),))
            conn.commit()
        except Exception as db_err:
            logger.error(f"Failed to log scraper failure in database: {db_err}")
        finally:
            conn.close()
            
    return scraped_jobs
