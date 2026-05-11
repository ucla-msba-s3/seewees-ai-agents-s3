# MSBA AI Agents Demo (LangGraph + LangChain)

Multi-agent system for operations/dispatch planning:
- Reads business context & KPI definitions from a PDF (RAG)
- Analyzes ops data from CSV (KPIs + anomaly detection)
- Pulls weather forecast and derives dispatch risk
- Produces a leadership-ready report
- Emails the report via Gmail SMTP (app password)

## Project Structure
- `data/` input PDF + CSV
- `src/` application code
- `chroma_db/` local vector store (not committed)
- `.env` secrets (not committed)

## Setup
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
windows: python -m pip install -r requirements.txt

cp .env.example .env
# For free-tier Gemini testing, fill GOOGLE_API_KEY from Google AI Studio.
# For OpenAI fallback, set LLM_PROVIDER=openai and fill OPENAI_API_KEY.
windows:  python src/main.py
```

## LLM Provider and Cost Guardrails

The app can run with either OpenAI or Gemini:

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=models/text-embedding-004
GOOGLE_API_KEY=your_google_ai_studio_key
```

For student/free testing, keep:

```env
GEMINI_FREE_TIER_ONLY=true
LLM_MAX_CALLS_PER_RUN=6
```

`GEMINI_FREE_TIER_ONLY=true` makes the app refuse Vertex AI / paid-mode settings. `LLM_MAX_CALLS_PER_RUN` stops runaway graph loops from making too many LLM calls in one process.

Important: the code cannot verify whether your Google project has billing enabled. To stay inside the free tier, create the key in Google AI Studio, do not upgrade the project to paid billing, and keep Google-side quotas/billing disabled.
