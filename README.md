<div align="center">

# 🤖 24/7 Autonomous Multi-Agent AI Orchestrator

**An enterprise-grade, cloud-deployed Multi-Agent AI Architecture managing 6 specialized autonomous sub-agents with real-time Telegram Command Center & scheduled intelligence briefings.**

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Multi--Agent_AI-Orchestrator-00A67E?style=for-the-badge&logo=openai&logoColor=white" />
  <img src="https://img.shields.io/badge/Telegram_Bot-Command_Center-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" />
  <img src="https://img.shields.io/badge/Cloud_Deployment-Render_24%2F7-46E3B7?style=for-the-badge&logo=render&logoColor=black" />
</p>

</div>

---

## 🌟 System Overview

The **Multi-Agent AI Orchestrator** is a production-ready autonomous system designed to automate deep web research, commercial lead discovery, software engineering tasks, data analytics, and global hackathon tracking. Instead of relying on a single monolithic prompt, a central **Master Orchestrator** dynamically routes tasks to **6 specialized sub-agents**, verifies output quality via an **Evaluator Agent**, and delivers actionable reports directly to Telegram.

---

## 🏗️ System Architecture (Mermaid Diagram)

```mermaid
flowchart TD
    User(["📱 User / Telegram Command Center"]) <-->|Real-Time Commands & Daily Briefings| Bot["⚡ Telegram Gateway & Scheduler"]
    Bot <--> Orchestrator["🧠 Master Orchestrator Engine"]

    Orchestrator --> A1["🔍 1. Research Agent\n(Deep Web & Market Intelligence)"]
    Orchestrator --> A2["💻 2. Coding Agent\n(Code Generation & Debugging)"]
    Orchestrator --> A3["📊 3. Data Agent\n(Analytics & Structured Insights)"]
    Orchestrator --> A4["🏆 4. Hackathon Agent\n(Daily 6:00 AM Global Competitions)"]
    Orchestrator --> A5["🎯 5. ClientHunter Agent\n(Daily 7:00 AM Commercial X-Ray)"]

    A1 & A2 & A3 & A4 & A5 --> Eval["🛡️ 6. QA Evaluator Agent\n(Fact-Checking & Quality Gate)"]
    Eval -->|Verified Output| Orchestrator
