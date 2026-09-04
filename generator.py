"""
generator.py
------------
Core logic for turning a raw feature / ADO requirement description into a
structured set of Agile artifacts using the Groq API:

    - Epics / Feature summary
    - User Stories (with priority & story points)
    - Tasks (per story)
    - Acceptance Criteria (Gherkin: Given/When/Then)
    - Test Cases / Test Scenarios (positive, negative, edge)
    - Definition of Done checklist

Groq exposes an OpenAI-compatible Chat Completions endpoint, so we reuse the
official `openai` Python SDK and simply point it at Groq's base URL. This
keeps the rest of the app (Flask UI, CLI, exporters) provider-agnostic — if
you ever want to switch back to OpenAI or another OpenAI-compatible
provider, just change GROQ_BASE_URL / GROQ_API_KEY (or add your own client
branch below).

The model is instructed to return strict JSON so downstream code can work
with a predictable schema.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI


# Groq's OpenAI-compatible endpoint.
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# A strong general-purpose Groq-hosted model with good JSON reliability.
# Other options at the time of writing: "llama-3.1-8b-instant" (faster/cheaper),
# "openai/gpt-oss-120b", "qwen3-32b". Check https://console.groq.com/docs/models
# for the current list.
DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# JSON schema we ask the model to follow. Keeping this in one place makes it
# easy to extend (e.g. add "risks" or "story_points") later.
# ---------------------------------------------------------------------------
ARTIFACT_JSON_SCHEMA_DESCRIPTION = """
Return ONLY valid JSON (no markdown fences, no commentary) matching exactly
this shape:

{
  "feature_summary": "string - concise restatement of the requirement",
  "epic": "string - one-line epic title this feature rolls up to",
  "user_stories": [
    {
      "id": "US-1",
      "title": "string",
      "story": "As a <role>, I want <goal>, so that <benefit>",
      "priority": "High | Medium | Low",
      "story_points": 1,
      "tasks": [
        {"id": "T-1", "description": "string", "type": "Dev | Test | Design | DevOps"}
      ],
      "acceptance_criteria": [
        {
          "id": "AC-1",
          "given": "string",
          "when": "string",
          "then": "string"
        }
      ],
      "test_scenarios": [
        {
          "id": "TC-1",
          "title": "string",
          "type": "Positive | Negative | Edge Case",
          "steps": ["step 1", "step 2"],
          "expected_result": "string"
        }
      ]
    }
  ],
  "definition_of_done": ["string", "string"],
  "assumptions_and_risks": ["string", "string"]
}

Rules:
- Generate 2 to 6 user stories depending on the complexity of the requirement.
- Every user story must have at least 2 tasks, 2 acceptance criteria, and 3
  test scenarios covering positive, negative, and edge cases.
- IDs must be unique and sequential across the whole document.
- Keep language concise and professional, suitable for pasting into Azure DevOps (ADO).
"""

SYSTEM_PROMPT = (
    "You are a senior business analyst and agile coach who converts raw "
    "product/feature requirements (as they would appear in Azure DevOps) "
    "into a complete, well-structured backlog: user stories, tasks, "
    "acceptance criteria, and test cases. You always respond with strict "
    "JSON only, following the exact schema you are given."
)


@dataclass
class GenerationResult:
    raw_json: Dict[str, Any]
    model: str
    requirement: str
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def _build_user_prompt(requirement: str, extra_context: str = "") -> str:
    context_block = f"\nAdditional context / constraints:\n{extra_context}\n" if extra_context else ""
    return (
        f"Feature / ADO Requirement:\n\"\"\"\n{requirement.strip()}\n\"\"\"\n"
        f"{context_block}\n"
        f"{ARTIFACT_JSON_SCHEMA_DESCRIPTION}"
    )


def _get_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAI:
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError(
            "No Groq API key found. Set the GROQ_API_KEY environment "
            "variable (or a .env file) or pass one in explicitly. "
            "Get one at https://console.groq.com/keys"
        )
    return OpenAI(api_key=key, base_url=base_url or GROQ_BASE_URL)


def _extract_json(content: str) -> str:
    """Strip markdown code fences some models add despite instructions not to."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def generate_artifacts(
    requirement: str,
    extra_context: str = "",
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.4,
) -> GenerationResult:
    """
    Calls the Groq API (OpenAI-compatible) and returns a GenerationResult
    with parsed JSON. Raises RuntimeError on missing API key; on parse
    failure, returns a GenerationResult with `error` set and `raw_json` as
    an empty dict.
    """
    if not requirement or not requirement.strip():
        raise ValueError("Requirement text must not be empty.")

    client = _get_client(api_key, base_url)
    user_prompt = _build_user_prompt(requirement, extra_context)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        # Most current Groq models (Llama 3.x, gpt-oss, qwen3) support native
        # JSON mode. Try it first for reliability.
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except Exception:
        # Fallback for models/providers that reject response_format.
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )

    content = response.choices[0].message.content or "{}"

    try:
        parsed = json.loads(_extract_json(content))
        return GenerationResult(raw_json=parsed, model=model, requirement=requirement)
    except json.JSONDecodeError as exc:
        return GenerationResult(
            raw_json={},
            model=model,
            requirement=requirement,
            error=f"Model did not return valid JSON: {exc}",
        )


# ---------------------------------------------------------------------------
# Formatting helpers - turn the JSON structure into human-friendly Markdown
# ---------------------------------------------------------------------------
def to_markdown(result: GenerationResult) -> str:
    data = result.raw_json
    if not data:
        return f"# Generation failed\n\n{result.error or 'Unknown error'}\n"

    lines: List[str] = []
    lines.append(f"# Agile Artifacts: {data.get('epic', 'Untitled Epic')}\n")
    lines.append(f"**Original Requirement:**\n> {result.requirement.strip()}\n")
    lines.append(f"**Feature Summary:** {data.get('feature_summary', '')}\n")

    for story in data.get("user_stories", []):
        lines.append(f"\n## {story.get('id', '')}: {story.get('title', '')}")
        lines.append(f"**Story:** {story.get('story', '')}")
        lines.append(
            f"**Priority:** {story.get('priority', 'N/A')}  |  "
            f"**Story Points:** {story.get('story_points', 'N/A')}"
        )

        lines.append("\n**Tasks:**")
        for task in story.get("tasks", []):
            lines.append(f"- [{task.get('id', '')}] ({task.get('type', '')}) {task.get('description', '')}")

        lines.append("\n**Acceptance Criteria:**")
        for ac in story.get("acceptance_criteria", []):
            lines.append(
                f"- **{ac.get('id', '')}** Given {ac.get('given', '')}, "
                f"When {ac.get('when', '')}, Then {ac.get('then', '')}"
            )

        lines.append("\n**Test Scenarios:**")
        for tc in story.get("test_scenarios", []):
            lines.append(f"- **{tc.get('id', '')}** ({tc.get('type', '')}) {tc.get('title', '')}")
            for i, step in enumerate(tc.get("steps", []), start=1):
                lines.append(f"    {i}. {step}")
            lines.append(f"    - *Expected:* {tc.get('expected_result', '')}")

    if data.get("definition_of_done"):
        lines.append("\n## Definition of Done")
        for item in data["definition_of_done"]:
            lines.append(f"- [ ] {item}")

    if data.get("assumptions_and_risks"):
        lines.append("\n## Assumptions & Risks")
        for item in data["assumptions_and_risks"]:
            lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def to_csv_rows(result: GenerationResult) -> List[Dict[str, str]]:
    """
    Flattens the structure into rows suitable for an ADO-style CSV import
    (one row per user story, with tasks/AC/test cases concatenated).
    """
    data = result.raw_json
    rows: List[Dict[str, str]] = []
    for story in data.get("user_stories", []):
        rows.append(
            {
                "Work Item Type": "User Story",
                "ID": story.get("id", ""),
                "Title": story.get("title", ""),
                "Description": story.get("story", ""),
                "Priority": story.get("priority", ""),
                "Story Points": str(story.get("story_points", "")),
                "Tasks": " | ".join(
                    f"{t.get('id')}: {t.get('description')} ({t.get('type')})"
                    for t in story.get("tasks", [])
                ),
                "Acceptance Criteria": " | ".join(
                    f"Given {a.get('given')}, When {a.get('when')}, Then {a.get('then')}"
                    for a in story.get("acceptance_criteria", [])
                ),
                "Test Scenarios": " | ".join(
                    f"{t.get('id')} ({t.get('type')}): {t.get('title')} -> {t.get('expected_result')}"
                    for t in story.get("test_scenarios", [])
                ),
            }
        )
    return rows
