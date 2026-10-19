import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import DB_PATH

class MemoryManager:
    """Manages persistent long-term storage and short-term session state using SQLite."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        # check_same_thread=False and 30s timeout to prevent multi-threaded Streamlit lock errors
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging (WAL) for high concurrency
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Sessions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Messages Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)

            # User Profile & Preferences (Procedural & Persona memory)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Task Execution & Sub-Agent Trajectories (Audit trail)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_trajectories (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_intent TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    final_report TEXT,
                    iterations INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            # Evaluation & Self-Correction Log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_logs (
                    id TEXT PRIMARY KEY,
                    trajectory_id TEXT NOT NULL,
                    iteration_index INTEGER NOT NULL,
                    subagent_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    verdict TEXT NOT NULL,
                    critique TEXT,
                    repaired_output TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trajectory_id) REFERENCES task_trajectories(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

            # Seed default user guidelines if not set
            cursor.execute("SELECT value FROM user_preferences WHERE key = 'assistant_rules'")
            if not cursor.fetchone():
                default_rules = (
                    "- Your official name is strictly SMART AI ASSISTANT in all capital letters.\n"
                    "- When introducing yourself or asked for your name, always say: \"আমি আপনার SMART AI ASSISTANT।\"\n"
                    "- GREETING: Always greet the user with the Islamic greeting: \"আসসালামু আলাইকুম\" (or \"আসসালামু আলাইকুম স্যার\").\n"
                    "- HONORIFIC: Always address the user with highest respect as \"স্যার\" (Sir) in every conversation, response, and report.\n"
                    "- ISLAMIC ETHICS & VALUES: Strictly remember, honor, and uphold Islamic principles, manners (আদব-আখলাক), and ethics in all discussions, advice, and behavior. Ensure all recommendations are halal, wholesome, and constructive.\n"
                    "- DEMEANOR & TONE: Be exceptionally humble (অত্যন্ত বিনয়ী), gentle (নম্র), respectful, polite, and patient at all times. Never display pride, arrogance, or harshness.\n"
                    "- Be extremely accurate, rigorous, and fact-grounded.\n"
                    "- Respond naturally and fluently in the user's spoken or preferred language (e.g. Bengali).\n"
                    "- Understand colloquial language, regional terms, and variations without getting confused.\n"
                    "- Delegate domain-specific sub-tasks to specialized agents.\n"
                    "- Always perform self-evaluation and fix errors before delivering the final report.\n"
                )
                cursor.execute(
                    "INSERT INTO user_preferences (key, value) VALUES (?, ?)",
                    ("assistant_rules", default_rules)
                )
                conn.commit()

    # Session Methods

    def create_session(self, title: str = "New Session") -> str:
        session_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title) VALUES (?, ?)",
                (session_id, title)
            )
            conn.commit()
        return session_id

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
            return [dict(r) for r in rows]

    def ensure_session(self, session_id: str, default_title: str = "Active Session"):
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (id, title) VALUES (?, ?)",
                    (session_id, default_title)
                )
                conn.commit()

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        self.ensure_session(session_id)
        msg_id = str(uuid.uuid4())
        meta_str = json.dumps(metadata or {})
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (msg_id, session_id, role, content, meta_str)
            )
            conn.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,)
            )
            conn.commit()

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,)
            ).fetchall()
            messages = []
            for r in rows:
                item = dict(r)
                item["metadata"] = json.loads(item["metadata_json"]) if item["metadata_json"] else {}
                messages.append(item)
            return messages

    # User Preferences
    def get_preference(self, key: str, default: str = "") -> str:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM user_preferences WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_preference(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                (key, value)
            )
            conn.commit()

    # Trajectory & Audit Trails
    def create_trajectory(self, session_id: str, user_intent: str, plan: Dict[str, Any]) -> str:
        self.ensure_session(session_id)
        traj_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO task_trajectories (id, session_id, user_intent, plan_json, status) VALUES (?, ?, ?, ?, 'in_progress')",
                (traj_id, session_id, user_intent, json.dumps(plan))
            )
            conn.commit()
        return traj_id

    def complete_trajectory(self, trajectory_id: str, final_report: str, iterations: int, status: str = "completed"):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE task_trajectories SET final_report = ?, iterations = ?, status = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (final_report, iterations, status, trajectory_id)
            )
            conn.commit()

    def log_evaluation(self, trajectory_id: str, iteration: int, subagent_name: str, score: float, verdict: str, critique: str, repaired_output: str = ""):
        eval_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO evaluation_logs (id, trajectory_id, iteration_index, subagent_name, score, verdict, critique, repaired_output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (eval_id, trajectory_id, iteration, subagent_name, score, verdict, critique, repaired_output)
            )
            conn.commit()
