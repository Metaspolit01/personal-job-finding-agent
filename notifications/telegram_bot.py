import logging
import asyncio
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.settings import DB_PATH
from database.db_manager import get_unsent_top_jobs
from database.memory_manager import (
    get_preferences,
    save_preference,
    add_conversation_turn,
    record_job_interaction,
    clear_conversation_history,
    get_job_details,
    auto_extract_profile_memory
)
from matching.llm_orchestrator import query_ollama_securely, query_ollama_agent_loop

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a greeting when the command /start is issued."""
    welcome_message = (
        "🤖 **Welcome to your Stateful AI Job Platform!** 👋\n\n"
        "I am actively monitoring job boards in the background and matching them using dynamic memory and adaptive scoring.\n\n"
        "**Available Commands:**\n"
        "🔹 `/list` - Trigger an active job scraping cycle & receive recommendations\n"
        "🔹 `/memory` - Inspect your current persistent profile and preferences\n"
        "🔹 `/memory reset` - Clear conversation logs & dynamic profile state\n"
        "🔹 `/id` - Show your active Telegram Chat ID for configuration\n\n"
        "💬 **Chat with me directly** to update interests (e.g., 'I want to focus on AWS and DevOps' or 'Suppress jobs from IgnoredInc')."
    )
    await update.message.reply_text(welcome_message, parse_mode="Markdown")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retrieve and display the active Telegram Chat ID to the user."""
    chat_id = update.effective_chat.id
    msg = (
        f"🆔 **Your Telegram Chat ID is:** `{chat_id}`\n\n"
        "Copy this number and set it as `TELEGRAM_CHAT_ID` in your `.env` file, then restart the application."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def list_jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Actively run the scraper, retrieve, and send the current top jobs."""
    chat_id = str(update.effective_chat.id)
    logger.info(f"User requested job list manually for chat {chat_id}. Triggering active search.")
    
    # Deliver any matched but unsent jobs immediately
    from database.db_manager import get_unsent_top_jobs, mark_as_sent
    from notifications.telegram_sender import send_jobs_to_telegram
    
    unsent = get_unsent_top_jobs(limit=10)
    if unsent:
        await update.message.reply_text("📥 *Found matched job recommendations in the database. Sending them now...*", parse_mode="Markdown")
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, send_jobs_to_telegram, unsent, chat_id)
        if success:
            job_ids = [j['job_id'] for j in unsent]
            mark_as_sent(job_ids)
            await update.message.reply_text("✅ *Pre-matched jobs delivered successfully!*", parse_mode="Markdown")
            
    await update.message.chat.send_action(action="typing")
    await update.message.reply_text("🔍 *Starting active scraper to search for new postings...* (This will take a moment)", parse_mode="Markdown")
    
    # Run the blocking scraper in a background thread under the scraper role context
    from scheduler.scheduler import run_job_search
    loop = asyncio.get_running_loop()
    
    def run_scraper_securely():
        return run_job_search(chat_id)
            
    await loop.run_in_executor(None, run_scraper_securely)

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display or edit persistent preference settings directly."""
    args = context.args
    
    if args and args[0].lower() == "reset":
        clear_conversation_history()
        save_preference("preferred_roles", ["DevOps", "Cloud Engineer", "SRE"])
        save_preference("preferred_technologies", ["Kubernetes", "Docker", "Terraform", "AWS", "Python"])
        save_preference("rejected_companies", ["IgnoredInc"])
        await update.message.reply_text("🔄 **Memory and conversation history cleared and reset to defaults.**")
        return
        
    if args and len(args) >= 3:
        sub = args[0].lower()
        value = " ".join(args[2:])
        
        prefs = get_preferences()
        
        if sub == "prefer":
            category = "preferred_technologies" if args[1].lower() == "tech" else "preferred_roles"
            current_list = prefs.get(category, [])
            if value not in current_list:
                current_list.append(value)
                save_preference(category, current_list)
                await update.message.reply_text(f"✅ Added *{value}* to your {category.replace('_', ' ')}!", parse_mode="Markdown")
                return
        elif sub == "reject" and args[1].lower() == "company":
            current_list = prefs.get("rejected_companies", [])
            if value not in current_list:
                current_list.append(value)
                save_preference("rejected_companies", current_list)
                await update.message.reply_text(f"✅ Added *{value}* to your rejected companies list!", parse_mode="Markdown")
                return

    # Default: Show memory profile
    prefs = get_preferences()
    pref_roles = prefs.get("preferred_roles", [])
    pref_tech = prefs.get("preferred_technologies", [])
    rejected_companies = prefs.get("rejected_companies", [])
    
    msg = (
        "🧠 **Persistent Profile State (SQLite Memory):**\n\n"
        f"🎯 **Preferred Roles:** {', '.join(pref_roles) if pref_roles else 'None'}\n"
        f"🛠️ **Preferred Technologies:** {', '.join(pref_tech) if pref_tech else 'None'}\n"
        f"🚫 **Rejected Companies:** {', '.join(rejected_companies) if rejected_companies else 'None'}\n\n"
        "💡 *Tips to edit profile:*\n"
        "👉 `/memory prefer tech Kubernetes` - Boost a technology\n"
        "👉 `/memory prefer role DevOps` - Boost a role\n"
        "👉 `/memory reject company StaffingCorp` - Blacklist a company\n"
        "👉 `/memory reset` - Wipe custom states"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chat messages with persistent conversational memory, dynamic profiling, and the agent loop."""
    user_message = update.message.text
    logger.info(f"User sent chat message: {user_message}")
    
    # Check if user is asking to trigger a manual job search cycle
    user_text_lower = user_message.lower()
    if "list" in user_text_lower and "job" in user_text_lower:
        await list_jobs_command(update, context)
        return
        
    await update.message.chat.send_action(action="typing")
    
    # 1. Dynamically analyze for name declarations and persist profile updates in SQLite
    auto_extract_profile_memory(user_message)
    
    # 2. Log user turn to persistent database memory
    add_conversation_turn("user", user_message)
    
    # 3. Create interactive placeholder message
    placeholder_msg = await update.message.reply_text("🤖 Thinking...")
    
    try:
        # Run agent ReAct reasoning loop
        final_reply = await query_ollama_agent_loop(user_message, session_id="default")
        
        if not final_reply.strip():
            final_reply = "I completed my analysis but didn't output a response."
            
        await placeholder_msg.edit_text(final_reply)
            
        # 4. Log assistant turn to persistent database memory
        add_conversation_turn("assistant", final_reply)
        
        # 5. Log dynamic LLM decision success
        from security.audit_logger import log_audit_action
        log_audit_action(
            tool="chat_handler",
            action="llm_chat",
            result="SUCCESS",
            details=f"Agent loop complete. Response length: {len(final_reply)}"
        )
        
    except Exception as e:
        logger.error(f"Error during agent chat loop: {e}")
        error_reply = "Sorry, my brain encountered an error or timed out."
        try:
            await placeholder_msg.edit_text(error_reply)
        except Exception:
            await update.message.reply_text(error_reply)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interactive inline keyboard clicks (Mark Applied or Ignore Job) under secure admin role."""
    query = update.callback_query
    await query.answer()  # Acknowledge Telegram callback immediately
    
    data = query.data
    logger.info(f"User clicked inline button callback: {data}")
    
    if ":" not in data:
        return
        
    action, job_id = data.split(":", 1)
    
    success = record_job_interaction(job_id, action)
        
    if success:
        original_text = query.message.text_html
        await query.edit_message_text(
            text=original_text,
            parse_mode="HTML",
            reply_markup=None
        )

async def resume_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle resume uploads, save text content, and track resume versions under admin role."""
    document = update.message.document
    if not document:
        return
        
    file_name = document.file_name.lower()
    if file_name.endswith(('.pdf', '.txt')):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        resume_dir = os.path.join(base_dir, "resumes")
        os.makedirs(resume_dir, exist_ok=True)
        
        # Clear old resume files (pdf/txt) so only active resume is evaluated
        for f in os.listdir(resume_dir):
            if f.endswith(('.pdf', '.txt')):
                try:
                    os.remove(os.path.join(resume_dir, f))
                except Exception:
                    pass
                
        target_path = os.path.join(resume_dir, document.file_name)
        
        await update.message.chat.send_action(action="typing")
        new_file = await context.bot.get_file(document.file_id)
        await new_file.download_to_drive(target_path)
        
        # Log upload as a memory event
        from security.audit_logger import log_audit_action
        log_audit_action(
            tool="resume_upload_handler",
            action="upload_resume",
            result="SUCCESS",
            details=f"Uploaded resume: {document.file_name}"
        )
            
        await update.message.reply_text(f"✅ Resume *{document.file_name}* uploaded and loaded into memory successfully!", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Please upload a resume in `.pdf` or `.txt` format.")


