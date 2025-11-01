from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
import requests
import json
import tempfile
import subprocess
import re
from typing import Optional

app = FastAPI(title="AI Code Review Backend with Auto-Fix")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Ollama settings ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "codellama"  # make sure to pull: ollama pull codellama


# ---------- Helper functions ----------

def call_ollama(prompt: str):
    """Send prompt to local LLM via Ollama."""
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        return f"[Error contacting LLM: {e}]"


def run_lint_check(code: str):
    """Run pylint and return main issues."""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w") as tmp:
            tmp.write(code)
            tmp_path = tmp.name
        result = subprocess.run(["pylint", tmp_path, "-rn", "--score", "n"],
                                capture_output=True, text=True)
        issues = []
        for line in result.stdout.splitlines():
            if re.search(r":\d+:", line):
                issues.append(line.strip())
        return issues[:5]
    except Exception:
        return []


def apply_fixes_to_code(code: str, feedback: list):
    """Try to apply suggested fixes based on LLM JSON feedback."""
    lines = code.splitlines()
    for fb in feedback:
        try:
            line_num = int(fb.get("line_number", -1))
            fix = fb.get("suggested_fix", "")
            if 1 <= line_num <= len(lines) and fix:
                # Replace the line or append modification as comment
                lines[line_num - 1] += f"  # FIX: {fix}"
        except Exception:
            continue
    return "\n".join(lines)


# ---------- Routes ----------

@app.post("/review")
async def review_code(code: str = Form(...), guidelines: Optional[str] = Form(None)):
    """Perform code review and automatic fix."""
    # --- 1. Static Linting ---
    lint_issues = run_lint_check(code)

    # --- 2. AI Review (JSON output) ---
    guidelines_text = f"\nGuidelines to follow: {guidelines}\n" if guidelines else "\n"
    system_prompt = (
        "You are a code review expert.\n"
        "Analyze the following Python code and produce a JSON list of findings.\n"
        "If guidelines are provided, prioritize them.\n"
        + guidelines_text +
        "Each finding must follow this format strictly (JSON only):\n"
        "[\n"
        "  {\n"
        "    \"issue_type\": \"bug/style/optimization/security\",\n"
        "    \"description\": \"short explanation\",\n"
        "    \"line_number\": 12,\n"
        "    \"suggested_fix\": \"short fix or replacement line\",\n"
        "    \"effort_estimate\": \"XS/S/M/L\",\n"
        "    \"doc_update\": \"what docs or comments to update\"\n"
        "  }\n"
        "]\n"
        "Provide ONLY valid JSON as output."
    )
    ai_response = call_ollama(system_prompt + "\n\nCode:\n" + code)

    try:
        feedback = json.loads(ai_response)
    except Exception:
        feedback = [{"issue_type": "general", "description": ai_response, "line_number": "-", "suggested_fix": ""}]

    # --- 3. Apply automatic fixes ---
    fixed_code = apply_fixes_to_code(code, feedback)

    # --- 4. Normalize/augment feedback with effort/doc_update ---
    for fb in feedback:
        if not isinstance(fb, dict):
            continue
        fb.setdefault("issue_type", "general")
        fb.setdefault("line_number", "-")
        fb.setdefault("suggested_fix", "")
        # Minimal heuristic effort if missing
        if not fb.get("effort_estimate"):
            it = (fb.get("issue_type") or "").lower()
            effort = "S"
            if it in {"bug", "security"}: effort = "M"
            if "refactor" in fb.get("description", "").lower(): effort = "M"
            if len((fb.get("suggested_fix") or "")) > 200: effort = "L"
            fb["effort_estimate"] = effort
        fb.setdefault("doc_update", "")

    return {
        "lint_issues": lint_issues,
        "ai_feedback": feedback,
        "fixed_code": fixed_code
    }


@app.post("/review_incremental")
async def review_code_incremental(
    code: str = Form(...),
    diff: Optional[str] = Form(None),
    guidelines: Optional[str] = Form(None),
):
    """Perform code review focusing on provided diff (incremental review)."""
    lint_issues = run_lint_check(code)

    focus = ("Focus primarily on the following diff hunks and their context.\n"
             f"Diff:\n{diff}\n") if diff else ""

    guidelines_text = f"\nGuidelines to follow: {guidelines}\n" if guidelines else "\n"

    system_prompt = (
        "You are a code review expert.\n"
        "Analyze the provided Python code.\n"
        + focus + guidelines_text +
        "Return a JSON array of findings with fields: issue_type, description, line_number, suggested_fix, effort_estimate (XS/S/M/L), doc_update.\n"
        "Only output JSON."
    )

    ai_response = call_ollama(system_prompt + "\n\nCode:\n" + code)
    try:
        feedback = json.loads(ai_response)
    except Exception:
        feedback = [{"issue_type": "general", "description": ai_response, "line_number": "-", "suggested_fix": ""}]

    fixed_code = apply_fixes_to_code(code, feedback)

    for fb in feedback:
        if not isinstance(fb, dict):
            continue
        fb.setdefault("issue_type", "general")
        fb.setdefault("line_number", "-")
        fb.setdefault("suggested_fix", "")
        if not fb.get("effort_estimate"):
            it = (fb.get("issue_type") or "").lower()
            effort = "S"
            if it in {"bug", "security"}: effort = "M"
            if "refactor" in fb.get("description", "").lower(): effort = "M"
            if len((fb.get("suggested_fix") or "")) > 200: effort = "L"
            fb["effort_estimate"] = effort
        fb.setdefault("doc_update", "")

    return {
        "lint_issues": lint_issues,
        "ai_feedback": feedback,
        "fixed_code": fixed_code,
        "mode": "incremental"
    }
