import os
import sys
import time
import threading
import urllib.request
import subprocess
import signal
import logging
from dotenv import load_dotenv
from agents.client_hunter_agent import ClientHunterAgent

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - [ServiceManager] - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("ServiceManager")

def keep_alive_worker():
    """Periodically sends an external HTTP request every 5 minutes to prevent Render Free tier from spinning down."""
    url = os.getenv("RENDER_EXTERNAL_URL") or "https://personal-ai-assistant-eviz.onrender.com"
    health_url = f"{url.rstrip('/')}/_stcore/health"
    local_health_url = "http://127.0.0.1:8501/_stcore/health"
    logger.info(f"Keep-alive monitor initialized (every 5 minutes) for {health_url}")
    time.sleep(20)
    while True:
        for target_url in (local_health_url, health_url):
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": "RenderKeepAlive/2.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    logger.info(f"Keep-alive ping sent to {target_url} - Status: {resp.status}")
            except Exception as e:
                logger.debug(f"Keep-alive ping note ({target_url}): {e}")
        time.sleep(300)  # Ping every 5 minutes (300s) so Render never sleeps

def main():
    if "--test-hunt" in sys.argv:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        logger.info("Running standalone ClientHunter & Business X-Ray test workflow...")
        hunter = ClientHunterAgent()
        res = hunter.execute_hunt_workflow(mark_as_scanned=False)
        print(res["audit_report_message"])
        print("\n" + "=" * 60 + "\n")
        print(res["proposal_letter_message"])
        return

    logger.info("Initializing 24/7 AI Assistant Microservices...")

    # Initialize ClientHunter & Business X-Ray persistent deduplication store
    try:
        hunter = ClientHunterAgent()
        logger.info(
            f"Sub-Agent Ready: {hunter.name} | Scanned DB: {hunter.store.storage_path} "
            f"(Daily 07:00 AM X-Ray Audit & 07:10 AM Smart Proposal Letter in UTC+6)"
        )
    except Exception as hunter_err:
        logger.warning(f"ClientHunter initialization note: {hunter_err}")

    # Start 24/7 keep-alive monitor in daemon thread
    t_keepalive = threading.Thread(target=keep_alive_worker, daemon=True)
    t_keepalive.start()

    processes = []

    # 1. Start Streamlit Web Dashboard
    streamlit_cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port=8501",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--browser.gatherUsageStats=false"
    ]
    logger.info("Launching Streamlit Web App on port 8501...")
    p_web = subprocess.Popen(streamlit_cmd)
    processes.append(p_web)

    # 2. Start Telegram Bot Worker (if token is configured)
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if tg_token and tg_token.strip() and tg_token != "your_telegram_bot_token_here":
        logger.info(
            "TELEGRAM_BOT_TOKEN found! Launching Telegram Bot Worker "
            "(with 06:00 AM Hackathon & 07:00 AM / 07:10 AM ClientHunter Schedulers)..."
        )
        p_tg = subprocess.Popen([sys.executable, "telegram_bot.py"])
        processes.append(p_tg)
    else:
        logger.info("TELEGRAM_BOT_TOKEN not configured yet. Telegram bot worker paused. Web UI is active.")

    def handle_shutdown(signum, frame):
        logger.info("Received termination signal. Gracefully shutting down all services...")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Health loop
    try:
        while True:
            time.sleep(5)

            # Monitor Streamlit web server
            if p_web.poll() is not None:
                logger.error(f"Streamlit web server stopped (code {p_web.poll()}). Rebooting container...")
                sys.exit(p_web.poll())

            # Monitor Telegram bot worker
            if tg_token and tg_token.strip() and tg_token != "your_telegram_bot_token_here":
                if p_tg is None or p_tg.poll() is not None:
                    exit_code = p_tg.poll() if p_tg else "None"
                    logger.warning(f"Telegram bot process exited (code {exit_code}). Re-launching worker...")
                    time.sleep(3)
                    p_tg = subprocess.Popen([sys.executable, "telegram_bot.py"])
    except KeyboardInterrupt:
        handle_shutdown(None, None)


if __name__ == "__main__":
    main()
