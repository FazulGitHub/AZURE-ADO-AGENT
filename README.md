# Agile Artifact Generator

Turn a raw feature / Azure DevOps (ADO) requirement into a full set of Agile
artifacts using [Groq](https://groq.com)'s fast LLM inference API:

- **User Stories** ("As a ... I want ... so that ...")
- **Tasks** per story (Dev / Test / Design / DevOps)
- **Acceptance Criteria** (Given / When / Then)
- **Test Scenarios / Test Cases** (Positive, Negative, Edge Case)
- **Definition of Done** checklist
- **Assumptions & Risks**

Two ways to use it: a small **Flask web app** with a form and downloads
(Markdown / JSON / CSV for ADO import), or a **CLI** for scripting.

---

## 1. Setup

```bash
# (recommended) create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# configure your Groq API key
cp .env.example .env
# then edit .env and set GROQ_API_KEY=gsk-...
```

You need a Groq API key — get one free at https://console.groq.com/keys.
The app defaults to the `openai/gpt-oss-120b` model; change `GROQ_MODEL`
in `.env` . See
https://console.groq.com/docs/models for the current model list.

## 2. Run the web app

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in your browser:

1. Paste your feature/requirement text (e.g. copied from an ADO work item).
2. Optionally add extra context/constraints (compliance, platforms, existing
   systems, etc.).
3. Click **Generate Artifacts**.
4. Review the generated backlog on the page, and download it as:
   - **Markdown** – for pasting into a wiki/Confluence/PR description.
   - **JSON** – for feeding into other tooling.
   - **CSV** – flattened, one row per user story, formatted to make
     importing into Azure DevOps (or Excel) straightforward.

## 3. Run from the command line

```bash
# inline text
python cli.py --requirement "Add Apple Pay support to mobile checkout" --format markdown

# from a file, save to disk
python cli.py --file sample_requirement.txt --format markdown --out artifacts.md
python cli.py --file sample_requirement.txt --format json --out artifacts.json
python cli.py --file sample_requirement.txt --format csv --out artifacts.csv

# choose a different model
python cli.py --file sample_requirement.txt --model llama-3.1-8b-instant
```

A ready-made `sample_requirement.txt` is included so you can try it right
away.

## 4. Project structure

```
agile_artifact_generator/
├── app.py                  # Flask web app (routes + download endpoints)
├── cli.py                  # Command-line interface
├── generator.py            # Core Groq prompt + JSON parsing + formatters
├── templates/
│   └── index.html          # Web UI page
├── static/
│   └── style.css           # Web UI styling
├── requirements.txt
├── .env.example
├── sample_requirement.txt
└── README.md
```

## 5. How it works

`generator.py` builds a single prompt containing:

1. The raw requirement text (and any extra context you supply).
2. A strict JSON schema description telling the model exactly what fields
   to return (user stories, tasks, acceptance criteria, test scenarios,
   definition of done, risks).

`generator.py` uses the official `openai` Python SDK, but points its
`base_url` at Groq's OpenAI-compatible endpoint
(`https://api.groq.com/openai/v1`) instead of OpenAI's — so no separate
`groq` package is required. The call requests
`response_format={"type": "json_object"}` for reliable JSON on models that
support it, with a plain-text fallback for those that don't; the response is
then parsed and rendered as Markdown/CSV/JSON by helper functions — no
fragile regex parsing of free text required.

## 6. Switching providers

Since `generator.py` just points the `openai` SDK at a different
`base_url`, you can swap in any OpenAI-compatible provider (OpenAI itself,
Groq, Together, Fireworks, a local vLLM/Ollama server, etc.) by setting:

```bash
GROQ_API_KEY=...        # or rename to whatever provider's key
GROQ_BASE_URL=...       # e.g. https://api.openai.com/v1 to go back to OpenAI
GROQ_MODEL=...          # a model name that provider supports
```

No code changes needed for any OpenAI-compatible endpoint.

## 7. Extending it

- **Different artifact types**: edit `ARTIFACT_JSON_SCHEMA_DESCRIPTION` in
  `generator.py` to add fields like `risk_level`, `dependencies`, or
  `non_functional_requirements`.
- **Direct ADO integration**: swap the CSV export for a call to the Azure
  DevOps REST API (`POST .../wit/workitems/$User%20Story`) using the parsed
  JSON — the data is already structured per story.
- **Multiple requirements at once**: loop over a list of requirements in
  `cli.py` and merge the resulting JSON documents.
- **Persistence**: replace the in-memory `_LAST_RESULT` in `app.py` with a
  database or session-backed store if you need multi-user support.

## 8. Notes & limits

- This is a local single-user tool by default (the Flask app keeps the last
  result in memory, not per-session) — fine for personal/dev use; add
  sessions or a DB before deploying for multiple concurrent users.
- Groq has a generous free tier; check current rate limits and pricing at
  https://console.groq.com/docs/rate-limits and https://groq.com/pricing.
- Never commit your real `.env` file / API key to source control.
