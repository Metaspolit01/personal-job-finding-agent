import requests
import json
import logging
import sqlite3
from config.settings import (
    LLM_PROVIDER,
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_API_BASE,
    OPENAI_MODEL,
    OPENAI_JSON_MODE,
    DB_PATH
)
from security.audit_logger import log_audit_action
from database.memory_manager import get_preferences, get_conversation_history

logger = logging.getLogger(__name__)

def build_personalized_system_prompt() -> str:
    """
    Construct a personalized, tool-aware system prompt containing
    user preferences and tool metadata definitions.
    """
    prefs = get_preferences()
    pref_roles = prefs.get("preferred_roles", ["DevOps", "Cloud Engineer", "SRE"])
    pref_tech = prefs.get("preferred_technologies", ["Kubernetes", "Docker", "Terraform", "AWS", "Python"])
    rejected_companies = prefs.get("rejected_companies", [])
    
    # Query SQLite profile memory for custom agent or user names
    agent_name = "your AI Job Search Assistant"
    user_name = "the user"
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT key, value FROM memory_entries WHERE category = 'user_profile'")
        rows = cursor.fetchall()
        for row in rows:
            if row["key"] == "agent_name":
                agent_name = row["value"]
            elif row["key"] == "user_name":
                user_name = row["value"]
    except Exception as e:
        logger.debug(f"Failed to fetch user_profile from database: {e}")
    finally:
        conn.close()
        
    # Build tool schemas dynamically from the registry
    from security.tool_registry import registry
    tools_metadata = registry.get_tools_metadata()
    tools_str = json.dumps(tools_metadata, indent=2)
    
    system_prompt = (
        f"You are {agent_name}, a friendly, professional, and autonomous AI Job Search Assistant for {user_name}.\n"
        f"You have high-privilege access to manage preferences, search job postings, rank jobs, and schedule monitoring workflows.\n\n"
        f"CURRENT USER PROFILE STATE:\n"
        f"- Target Roles: {', '.join(pref_roles) if pref_roles else 'None'}\n"
        f"- Target Technologies: {', '.join(pref_tech) if pref_tech else 'None'}\n"
    )
    
    if rejected_companies:
        system_prompt += f"- Suppressed Companies: {', '.join(rejected_companies)}\n"
        
    system_prompt += (
        f"\nAVAILABLE TOOLS:\n"
        f"{tools_str}\n\n"
        f"RESPONSE FORMAT INSTRUCTIONS:\n"
        f"You must respond ONLY with a single valid JSON object. Do not wrap your response in markdown backticks or output extra characters. "
        f"The JSON object must match this schema exactly:\n"
        f"{{\n"
        f"  \"thought\": \"Detailed reasoning about what to do next or why you are giving the final response.\",\n"
        f"  \"tool_calls\": [\n"
        f"    {{\n"
        f"      \"name\": \"tool_name\",\n"
        f"      \"arguments\": {{\n"
        f"        \"arg_name\": \"arg_value\"\n"
        f"      }}\n"
        f"    }}\n"
        f"  ],\n"
        f"  \"final_response\": \"Your final response message to the user. Leave this empty if you are invoking tools.\"\n"
        f"}}\n\n"
        f"AGENT RULES:\n"
        f"1. To run actions (e.g. search jobs, update preferences, create task), populate 'tool_calls' and keep 'final_response' empty.\n"
        f"2. You will receive the tool output as an Observation in the next turn. Then you can reason and call more tools if needed.\n"
        f"3. When tool execution is finished or no actions are required, fill 'final_response' and leave 'tool_calls' empty.\n"
        f"4. Do NOT mention database tables, JSON keys, or tool schemas in your chat replies to the user. Keep it natural."
    )
    
    return system_prompt

def query_llm_securely(prompt: str, json_format: bool = False, session_id: str = "default") -> str:
    """
    Direct prompt query to the configured LLM (Ollama or OpenAI-compatible API).
    """
    import time
    start_time = time.perf_counter()
    try:
        if LLM_PROVIDER.lower() == "openai":
            if not OPENAI_API_KEY:
                logger.error("OPENAI_API_KEY is not configured in settings.")
                return ""
            
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "stream": False
            }
            if json_format and OPENAI_JSON_MODE:
                payload["response_format"] = {"type": "json_object"}
                
            url = f"{OPENAI_API_BASE.rstrip('/')}/chat/completions"
            logger.info(f"Direct LLM query: Dispatching to OpenAI-compatible API ({OPENAI_MODEL})...")
            
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            response_text = data["choices"][0]["message"]["content"].strip()
        else:
            # Default to Ollama
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }
            if json_format:
                payload["format"] = "json"
                
            logger.info(f"Direct LLM query: Dispatching to Ollama ({OLLAMA_MODEL})...")
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            response_text = data.get("response", "").strip()
            
        duration = time.perf_counter() - start_time
        try:
            from monitoring.metrics_collector import ai_response_latency
            ai_response_latency.observe(duration)
        except Exception:
            pass
            
        log_audit_action(tool="query_llm_securely", action="direct_inference", result="SUCCESS")
        return response_text
    except Exception as e:
        log_audit_action(tool="query_llm_securely", action="direct_inference", result="FAILED", details=str(e))
        logger.error(f"Direct LLM call failed: {e}")
        return ""

async def query_llm_agent_loop(prompt: str, session_id: str = "default") -> str:
    """
    Run an autonomous reasoning loop (max 4 turns) to fulfill user requests using tools.
    Supports local Ollama and OpenAI-compatible API providers.
    """
    from security.tool_registry import registry
    
    iteration = 0
    max_iterations = 4
    observations = []
    
    current_prompt = prompt
    
    while iteration < max_iterations:
        iteration += 1
        system_prompt = build_personalized_system_prompt()
        chat_history = get_conversation_history(limit=8, session_id=session_id)
        
        import time
        start_time = time.perf_counter()
        
        try:
            if LLM_PROVIDER.lower() == "openai":
                if not OPENAI_API_KEY:
                    logger.error("OPENAI_API_KEY is not configured.")
                    return "Sorry, the OpenAI API key is missing."
                
                # Format messages array for Chat Completion API
                messages = [
                    {"role": "system", "content": system_prompt}
                ]
                if chat_history:
                    for turn in chat_history:
                        messages.append({"role": turn["role"], "content": turn["content"]})
                
                # Construct user content with observations
                user_content = ""
                if observations:
                    user_content += "\n=== CURRENT TOOL EXECUTION OBSERVATIONS ===\n"
                    for obs in observations:
                        user_content += f"Tool Called: {obs['tool']}\nArguments: {obs['args']}\nObservation Result: {obs['result']}\n\n"
                    user_content += "===========================================\n\n"
                
                user_content += f"User Prompt: {current_prompt}"
                messages.append({"role": "user", "content": user_content})
                
                payload = {
                    "model": OPENAI_MODEL,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.2
                }
                if OPENAI_JSON_MODE:
                    payload["response_format"] = {"type": "json_object"}
                
                url = f"{OPENAI_API_BASE.rstrip('/')}/chat/completions"
                logger.info(f"Agent Loop [Turn {iteration}/{max_iterations}]: Querying OpenAI-compatible API ({OPENAI_MODEL})...")
                
                import httpx
                headers = {
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload, headers=headers, timeout=120.0)
                    response.raise_for_status()
                    data = response.json()
                    response_text = data["choices"][0]["message"]["content"].strip()
            else:
                # Default to Ollama
                history_text = ""
                if chat_history:
                    history_text = "\n=== RECENT CONVERSATION HISTORY ===\n"
                    for turn in chat_history:
                        history_text += f"{turn['role'].capitalize()}: {turn['content']}\n"
                    history_text += "===================================\n\n"
                    
                observation_text = ""
                if observations:
                    observation_text = "\n=== CURRENT TOOL EXECUTION OBSERVATIONS ===\n"
                    for obs in observations:
                        observation_text += f"Tool Called: {obs['tool']}\nArguments: {obs['args']}\nObservation Result: {obs['result']}\n\n"
                    observation_text += "===========================================\n\n"
                    
                full_prompt = (
                    f"{system_prompt}\n"
                    f"{history_text}"
                    f"{observation_text}"
                    f"User Prompt: {current_prompt}\n"
                    f"Assistant (Respond ONLY in the JSON schema defined above):"
                )
                
                payload = {
                    "model": OLLAMA_MODEL,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json"
                }
                
                logger.info(f"Agent Loop [Turn {iteration}/{max_iterations}]: Querying Ollama ({OLLAMA_MODEL})...")
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.post(OLLAMA_API_URL, json=payload, timeout=120.0)
                    response.raise_for_status()
                    data = response.json()
                    response_text = data.get("response", "").strip()
            
            duration = time.perf_counter() - start_time
            try:
                from monitoring.metrics_collector import ai_response_latency
                ai_response_latency.observe(duration)
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Agent loop call failed: {e}")
            log_audit_action(tool="llm_agent_loop", action="inference", result="FAILED", details=str(e))
            return f"Sorry, I had trouble connecting to the LLM. Error: {e}"
            
        # Parse JSON schema
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                except Exception:
                    parsed = {"final_response": response_text, "tool_calls": []}
            else:
                parsed = {"final_response": response_text, "tool_calls": []}
                
        thought = parsed.get("thought", "")
        tool_calls = parsed.get("tool_calls", [])
        final_response = parsed.get("final_response", "")
        
        logger.info(f"Agent Thought: {thought}")
        log_audit_action(tool="llm_agent_loop", action="reasoning", result="SUCCESS", details=f"Thought: {thought}")
        
        if not tool_calls:
            if not final_response:
                final_response = "I have successfully processed your request."
            return final_response
            
        # Execute tool calls
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})
            
            logger.info(f"Agent triggering tool '{tool_name}' with arguments {tool_args}")
            
            import asyncio
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, registry.call_tool, tool_name, tool_args)
            
            observations.append({
                "tool": tool_name,
                "args": tool_args,
                "result": str(result)
            })
            
    return "I completed my operations but reached the recursion limit before outputting a final response."

# Backward compatibility aliases
query_ollama_securely = query_llm_securely
query_ollama_agent_loop = query_llm_agent_loop
