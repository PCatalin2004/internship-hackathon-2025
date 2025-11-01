from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
import requests
import json
import tempfile
import subprocess
import re

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
async def review_code(code: str = Form(...)):
    """Perform code review and automatic fix."""
    # --- 1. Static Linting ---
    lint_issues = run_lint_check(code)

    # --- 2. AI Review (JSON output) ---
    system_prompt = """You are a code review expert.
Analyze the following Python code and produce a JSON list of findings.
Each finding must follow this format:
[
  {
    "issue_type": "bug/style/optimization/security",
    "description": "short explanation",
    "line_number": 12,
    "suggested_fix": "short fix or replacement line"
  }
]
Provide ONLY valid JSON as output.
"""
    ai_response = call_ollama(system_prompt + "\n\nCode:\n" + code)

    try:
        feedback = json.loads(ai_response)
    except Exception:
        feedback = [{"issue_type": "general", "description": ai_response, "line_number": "-", "suggested_fix": ""}]

    # --- 3. Apply automatic fixes ---
    fixed_code = apply_fixes_to_code(code, feedback)

    return {
        "lint_issues": lint_issues,
        "ai_feedback": feedback,
        "fixed_code": fixed_code
    }
