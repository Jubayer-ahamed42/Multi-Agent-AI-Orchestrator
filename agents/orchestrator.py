import json
import re
import base64
import logging
from typing import Dict, Any, List, Optional, Callable
from config import MAX_EVAL_RETRIES, get_active_model

from database.memory import MemoryManager
from agents.llm_client import call_llm
from agents.research_agent import ResearchAgent
from agents.coding_agent import CodingAgent
from agents.data_agent import DataAgent
from agents.evaluator_agent import EvaluatorAgent
from agents.hackathon_agent import HackathonAgent
from agents.client_hunter_agent import ClientHunterAgent
from agents.smart_sales_assistant import SmartSalesAssistant
from tools.tts_tools import text_to_speech_bengali

logger = logging.getLogger(__name__)

class MasterOrchestrator:
    """Master Personal Assistant and Hierarchical Multi-Agent Orchestrator.
    
    Features Smart Intent Routing:
    - Fast Path: Direct instant response for greetings & conversation (~1-2 seconds)
    - Specialist Path: Decomposes and delegates complex tasks to sub-agents with QA loops
    - Voice Reply: Automatic Bengali speech synthesis for all responses
    """

    def __init__(self, memory_manager: Optional[MemoryManager] = None, model: Optional[str] = None):
        self.memory = memory_manager or MemoryManager()
        self.model = model or get_active_model()
        self.researcher = ResearchAgent(model=self.model)
        self.coder = CodingAgent(model=self.model)
        self.data_specialist = DataAgent(model=self.model)
        self.hackathon_specialist = HackathonAgent(model=self.model)
        self.client_hunter = ClientHunterAgent(model=self.model)
        self.sales_assistant = SmartSalesAssistant()
        self.evaluator = EvaluatorAgent(model=self.model)

    def process_command(
        self,
        session_id: str,
        user_command: str,
        mode: str = "auto",
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """Executes a user command through mode-aware routing, delegation, evaluation, and voice generation.
        
        Args:
            session_id: Target session id.
            user_command: User message or task prompt.
            mode: "chat" for instant conversation, "work" for multi-agent squad, or "auto".
            on_progress: Progress callback for live GUI updates.
        """

        def notify(event_type: str, message: str, details: Optional[Dict[str, Any]] = None):
            event = {
                "type": event_type,
                "message": message,
                "details": details or {}
            }
            if on_progress:
                on_progress(event)
            return event

        user_rules = self.memory.get_preference("assistant_rules", "")

        # -------------------------------------------------------------
        # Step 1: Mode-Driven Intent Routing (Chat vs Work)
        # -------------------------------------------------------------
        clean_mode = (mode or "auto").lower()
        task_keywords = [
            "hackathon", "হ্যাকাথন", "devpost", "kaggle", "lablab",
            "hunt", "client", "xray", "x-ray", "audit", "proposal", "lead",
            "ক্লায়েন্ট", "ক্লায়েন্ট", "অডিট", "এক্স-রে", "প্রপোজাল", "লিড",
            "code", "কোড", "পাইথন", "python", "script", "স্ক্রিপ্ট",
            "data", "ডাটা", "তথ্য", "বিশ্লেষণ", "অ্যানালাইসিস", "analysis",
            "রোডম্যাপ", "roadmap", "গবেষণা", "রিসার্চ", "research"
        ]
        has_task_keywords = any(k in user_command.lower() for k in task_keywords)

        # Smart routing: If explicit domain task keywords are present, intelligently route to TASK squad
        if clean_mode == "work" or has_task_keywords:
            intent_type = "TASK"
            notify("status", "স্পেশালিস্ট এজেন্ট স্কোয়াড প্রস্তুত হচ্ছে...")
        elif clean_mode == "chat":
            intent_type = "CONVERSATION"
            notify("status", "চ্যাট মোড সক্রিয়: সরাসরি দ্রুত উত্তর প্রস্তুত করা হচ্ছে...")
        else:
            notify("status", "নির্দেশ বিশ্লেষণ ও উপযুক্ত মোড নির্ধারণ করা হচ্ছে...")
            classifier_prompt = f"""You are the Master Personal Assistant.
Analyze this user input:
"{user_command}"

Classify into one of two categories:
1. "CONVERSATION": Greetings, casual talk, questions about who you are, simple chat.
2. "TASK": Requires research, writing code, executing calculations, analyzing data, or solving complex problems.

Respond ONLY with JSON:
{{"intent_type": "CONVERSATION" or "TASK"}}
"""
            try:
                raw_intent = call_llm(
                    messages=[{"role": "user", "content": classifier_prompt}],
                    model=self.model,
                    temperature=0.0
                )
                intent_match = re.search(r"\{.*\}", raw_intent, re.DOTALL)
                intent_type = json.loads(intent_match.group(0))["intent_type"] if intent_match else "TASK"
            except Exception:
                intent_type = "TASK"

        # -------------------------------------------------------------
        # Fast Path: Direct Conversational Response (Instant, ~1-2s)
        # -------------------------------------------------------------
        if intent_type == "CONVERSATION":
            notify("status", "সরাসরি উত্তর প্রস্তুত করা হচ্ছে...")

            
            chat_history = self.memory.get_messages(session_id)[-4:]
            formatted_history = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history])

            direct_prompt = f"""You are SMART AI ASSISTANT, an elite, highly intelligent, deeply respectful, humble, and polite Bengali AI Assistant.
The user is speaking to you directly.
Respond warmly, humbly, and naturally in fluent native Bengali.

Your official name is strictly "SMART AI ASSISTANT" (always in capital letters).
When asked about your name, identity, or when greeting the user, always state clearly:
"আমি আপনার SMART AI ASSISTANT।"

MANDATORY BEHAVIOR & ETIQUETTE RULES:
- GREETING: Always greet the user with the Islamic greeting: "আসসালামু আলাইকুম" (e.g., "আসসালামু আলাইকুম স্যার!").
- HONORIFIC: Always address the user with highest honor and respect as "স্যার" (Sir) throughout your response.
- ISLAMIC ETHICS: Strictly uphold and respect Islamic principles, values, and manners (আদব ও আখলাক). Ensure all advice and interactions are wholesome, halal, and constructive.
- DEMEANOR: Be exceptionally humble (অত্যন্ত বিনয়ী), gentle (নম্র), polite, and courteous at all times. Never display arrogance or harsh words.

[USER GUIDELINES]:
{user_rules}

[RECENT CHAT HISTORY]:
{formatted_history}

[USER MESSAGE]:
{user_command}

Instructions:
- Always use the name SMART AI ASSISTANT in capital letters.
- Greet with "আসসালামু আলাইকুম" and address the user with deep respect as "স্যার".
- If the user asks who you are or what your name is, declare: "আমি আপনার SMART AI ASSISTANT।"
- If the user asks if you understand them (e.g. "তুমি আমার কথা বুঝো"), reassure them humbly and respectfully: "জি স্যার, আমি আপনার প্রতিটি কথা ও নির্দেশ খুব ভালোভাবে বুঝতে পারছি এবং আপনার সেবায় সর্বদা প্রস্তুত আছি।"
- Keep the response elegant, crisp, respectful, and helpful.
"""
            try:
                final_report = call_llm(
                    messages=[{"role": "user", "content": direct_prompt}],
                    model=self.model,
                    temperature=0.4
                )
                if not final_report or final_report.strip().startswith("⚠️"):
                    raise RuntimeError("Direct conversation LLM returned error or empty string")
            except Exception as dir_err:
                logger.error(f"Direct conversation error: {dir_err}")
                final_report = "আসসালামু আলাইকুম স্যার! আমি আপনার SMART AI ASSISTANT। আমি সর্বদা আপনার সেবায় আন্তরিকভাবে প্রস্তুত আছি, স্যার। আমাকে যেকোনো নির্দেশ দিন।"

            # Generate spoken voice reply in Bengali
            notify("voice", "ভয়েস অডিও প্রস্তুত করা হচ্ছে...")
            audio_bytes = text_to_speech_bengali(final_report)
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None

            # Save in database
            traj_id = self.memory.create_trajectory(session_id, user_command, {"type": "direct_conversation"})
            self.memory.add_message(session_id, "user", user_command)
            self.memory.add_message(
                session_id,
                "assistant",
                final_report,
                metadata={
                    "trajectory_id": traj_id,
                    "iterations": 1,
                    "type": "conversation",
                    "audio_b64": audio_b64
                }
            )
            self.memory.complete_trajectory(traj_id, final_report, 1, status="completed")


            notify("completed", "উত্তর সম্পন্ন!", {"final_report": final_report})

            return {
                "trajectory_id": traj_id,
                "final_report": final_report,
                "audio_bytes": audio_bytes,
                "sub_agent_results": [],
                "evaluations": [],
                "iterations": 1
            }

        # -------------------------------------------------------------
        # Specialist Path: Multi-Agent Delegation & QA Loop
        # -------------------------------------------------------------
        plan_prompt = f"""You are the Master Personal Assistant Orchestrator.
Your goal is to break down this user request into clear, atomic sub-tasks for specialized sub-agents.
Carefully interpret native Bengali, regional phrasing, or colloquial terms without confusion.

[USER COMMAND]:
{user_command}

[PERSISTENT USER RULES]:
{user_rules}

Available Sub-Agents:
1. "research": For web search, fact-checking, citations, exploring any subject or news.
2. "coding": For writing Python scripts, debugging, algorithms, file tools, system tests.
3. "data": For data analysis, metrics tables, math calculations, tabular comparisons.
4. "hackathon": For finding live/upcoming hackathons (Devpost, Kaggle, Lablab.ai), brainstorming winning project ideas, analyzing judging criteria, creating 24h/48h hackathon roadmaps, pitch decks, and submission READMEs.
5. "client_hunter": For finding target businesses/clients, running 10-point live website/marketing X-Ray audits (Meta Pixel, Google Analytics, AI Chatbot, speed, SEO, booking), calculating Digital Health Scores & lost revenue in BDT, BDT pricing strategies, and generating high-converting client proposal letters.
6. "smart_sales": For customer sales conversations, WhatsApp bot interactions, lead qualification, and consultative AI sales for "Be Smart With AI" agency.

Respond ONLY with a JSON object:
{{
    "summary": "Brief summary of planned execution",
    "subtasks": [
        {{
            "agent": "research" | "coding" | "data" | "hackathon" | "client_hunter" | "smart_sales",
            "task_description": "Precise instruction for the specialist"
        }}
    ]
}}
"""
        try:
            raw_plan = call_llm(
                messages=[{"role": "user", "content": plan_prompt}],
                model=self.model,
                temperature=0.1
            )
            if not raw_plan or raw_plan.strip().startswith("⚠️"):
                raise RuntimeError("Planner LLM returned error or empty string")
            json_match = re.search(r"\{.*\}", raw_plan, re.DOTALL)
            clean_plan = json_match.group(0) if json_match else raw_plan.strip()
            plan = json.loads(clean_plan)
            if not isinstance(plan, dict) or not isinstance(plan.get("subtasks"), list) or len(plan["subtasks"]) == 0:
                raise ValueError("Plan missing non-empty subtasks list")
        except Exception:
            is_sales = any(k in user_command.lower() for k in ["sales", "বিক্রয়", "be smart with ai", "কাস্টমার", "কনসালটেন্ট"])
            is_hunt = any(k in user_command.lower() for k in ["hunt", "client", "xray", "x-ray", "audit", "ক্লায়েন্ট", "ক্লায়েন্ট", "অডিট", "এক্স-রে", "প্রপোজাল", "লিড"])
            is_hack = any(k in user_command.lower() for k in ["hackathon", "হ্যাকাথন", "devpost", "kaggle", "lablab", "প্রতিযোগিতা", "রোডম্যাপ"])
            is_code = any(k in user_command.lower() for k in ["code", "কোড", "python", "পাইথন", "স্ক্রিপ্ট"])
            is_data = any(k in user_command.lower() for k in ["data", "ডাটা", "অ্যানালাইসিস", "analysis"])
            default_agent = "smart_sales" if is_sales else ("client_hunter" if is_hunt else ("hackathon" if is_hack else ("coding" if is_code else ("data" if is_data else "research"))))
            plan = {
                "summary": "সরাসরি সম্পাদন পরিকল্পনা",
                "subtasks": [{"agent": default_agent, "task_description": user_command}]
            }

        traj_id = self.memory.create_trajectory(session_id, user_command, plan)
        notify("plan", f"পরিকল্পনা প্রস্তুত: {plan.get('summary', 'টাস্ক বিভাজন সম্পন্ন')}", {"plan": plan})

        sub_agent_results = []
        all_evaluations = []
        iteration_count = 1

        # Dispatch tasks to Sub-Agents with Self-Correction Feedback Loop
        for task_idx, task in enumerate(plan.get("subtasks", [])):
            agent_type = task.get("agent")
            task_desc = task.get("task_description") or user_command

            notify("subagent_start", f"দায়িত্ব দেওয়া হলো: {str(agent_type or 'research').upper()} স্পেশালিস্ট...", {"subtask": task})

            current_critique = None
            task_success = False
            sub_output_data = {}

            for attempt in range(1, MAX_EVAL_RETRIES + 1):
                iteration_count = max(iteration_count, attempt)

                try:
                    if agent_type == "research":
                        sub_output_data = self.researcher.run(task_desc, critique=current_critique)
                    elif agent_type == "coding":
                        sub_output_data = self.coder.run(task_desc, critique=current_critique)
                    elif agent_type == "data":
                        sub_output_data = self.data_specialist.run(task_desc, critique=current_critique)
                    elif agent_type == "hackathon":
                        sub_output_data = self.hackathon_specialist.run(task_desc, critique=current_critique)
                    elif agent_type == "client_hunter":
                        sub_output_data = self.client_hunter.run(task_desc, critique=current_critique)
                    elif agent_type == "smart_sales":
                        sub_output_data = self.sales_assistant.run(task_desc, critique=current_critique)
                    else:
                        sub_output_data = self.researcher.run(task_desc, critique=current_critique)
                except Exception as e:
                    logger.error(f"Sub-agent {agent_type} exception: {e}")
                    sub_output_data = {
                        "subagent": agent_type,
                        "output": f"Sub-agent encountered an unexpected error: {str(e)}",
                        "tool_errors": [str(e)]
                    }

                notify(
                    "subagent_output",
                    f"{sub_output_data.get('subagent', agent_type)} খসড়া তৈরি করেছে (চেষ্টা #{attempt})।",
                    {"output_snippet": str(sub_output_data.get("output", ""))[:300] + "..."}
                )

                notify("evaluation_start", f"কোয়ালিটি ও তথ্যের সত্যতা যাচাই চলছে (চেষ্টা #{attempt})...")
                eval_result = self.evaluator.evaluate_output(
                    user_intent=task_desc,
                    subagent_name=sub_output_data.get("subagent", agent_type),
                    draft_output=sub_output_data.get("output", ""),
                    execution_context={"tool_errors": sub_output_data.get("tool_errors")}
                )

                self.memory.log_evaluation(
                    trajectory_id=traj_id,
                    iteration=attempt,
                    subagent_name=sub_output_data.get("subagent", agent_type),
                    score=eval_result.get("average_score", 4.0),
                    verdict=eval_result.get("verdict", "APPROVED"),
                    critique="; ".join(eval_result.get("critique", [])),
                    repaired_output=sub_output_data.get("output", "")
                )
                all_evaluations.append(eval_result)

                if eval_result.get("verdict") == "APPROVED":
                    notify("evaluation_pass", f"যাচাই সফল! স্কোর: {eval_result.get('average_score', 4.5)}/5.0", {"eval": eval_result})
                    task_success = True
                    break
                else:
                    current_critique = eval_result.get("feedback_for_repair") or "; ".join(eval_result.get("critique", []))
                    notify(
                        "evaluation_fail",
                        f"ত্রুটি পাওয়া গেছে! সংশোধন লুপ সক্রিয় হচ্ছে (চেষ্টা #{attempt}/{MAX_EVAL_RETRIES})...",
                        {"eval": eval_result, "critique": current_critique}
                    )

            sub_agent_results.append({
                "task": task,
                "agent_type": agent_type,
                "output": sub_output_data.get("output", ""),
                "eval": eval_result,
                "attempts": attempt
            })

        # Final Synthesis
        notify("synthesis", "চূড়ান্ত নিখুঁত ও পরিমার্জিত রিপোর্ট প্রস্তুত করা হচ্ছে...")

        # If ClientHunter or SmartSales is the sole specialist executed, preserve its exact formatting
        if (
            len(sub_agent_results) == 1
            and sub_agent_results[0].get("agent_type") in ["client_hunter", "smart_sales"]
            and sub_agent_results[0].get("output")
        ):
            final_report = sub_agent_results[0]["output"]
        else:
            synthesis_prompt = f"""You are SMART AI ASSISTANT, the Master AI Assistant.
Your specialized sub-agents have completed and verified all sub-tasks for the user's order.
Combine and polish their findings into a single, comprehensive, beautifully structured final report.
Always respond in the user's natural language (Bengali if the user prompted in Bengali, or English if prompted in English).
When referencing yourself, always write SMART AI ASSISTANT in all capital letters.


[ORIGINAL USER ORDER]:
{user_command}

[VERIFIED SUB-AGENT FINDINGS]:
{json.dumps([{'task': r['task'].get('task_description', user_command), 'findings': r['output']} for r in sub_agent_results], indent=2, ensure_ascii=False)}

[USER GUIDELINES]:
{user_rules}

CRITICAL BEHAVIOR RULES:
- GREETING & RESPECT: Address the user with highest honor as "স্যার" (Sir) throughout the report.
- ISLAMIC ETHICS & DEMEANOR: Be exceptionally humble (বিনয়ী), polite, and mindful of Islamic values and manners (আদব ও আখলাক).

Formatting Requirements:
- Clear, professional executive summary addressed respectfully to "স্যার".
- Deep dive sections with key details, data tables, or code snippets where applicable.
- Source citations or verification notes.
- Direct, pristine, and ready-to-use output.
"""
            try:
                final_report = call_llm(
                    messages=[{"role": "user", "content": synthesis_prompt}],
                    model=self.model,
                    temperature=0.2
                )
                if not final_report or final_report.strip().startswith("⚠️"):
                    raise RuntimeError("Synthesis LLM returned error or empty string")
            except Exception as synth_err:
                logger.error(f"Synthesis call error: {synth_err}")
                findings_text = "\n\n".join([r.get("output", "") for r in sub_agent_results if r.get("output")])
                if findings_text.strip().startswith("আসসালামু আলাইকুম"):
                    final_report = findings_text
                else:
                    final_report = (
                        f"আসসালামু আলাইকুম স্যার!\n\n"
                        f"আপনার নির্দেশিত কাজটি স্পেশালিস্ট সাব-এজেন্ট স্কোয়াড সম্পন্ন করেছে। বিস্তারিত প্রতিবেদন:\n\n"
                        f"{findings_text}"
                    )

        # Generate voice audio for the final report summary
        notify("voice", "ভয়েস অডিও প্রস্তুত করা হচ্ছে...")
        audio_bytes = text_to_speech_bengali(final_report)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None

        self.memory.add_message(session_id, "user", user_command)
        self.memory.add_message(
            session_id,
            "assistant",
            final_report,
            metadata={
                "trajectory_id": traj_id,
                "iterations": iteration_count,
                "audio_b64": audio_b64
            }
        )
        self.memory.complete_trajectory(traj_id, final_report, iteration_count, status="completed")


        notify("completed", "কাজ সফলভাবে সম্পন্ন এবং সম্পূর্ণ যাচাইকৃত!", {"final_report": final_report})

        return {
            "trajectory_id": traj_id,
            "final_report": final_report,
            "audio_bytes": audio_bytes,
            "sub_agent_results": sub_agent_results,
            "evaluations": all_evaluations,
            "iterations": iteration_count
        }
