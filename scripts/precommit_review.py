import subprocess
import sys
import json
import os
from urllib import request, parse


def get_staged_python_files():
    res = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], capture_output=True, text=True)
    files = [f.strip() for f in res.stdout.splitlines() if f.strip().endswith('.py')]
    return files


def get_staged_diff_for(files):
    if not files:
        return ""
    cmd = ["git", "diff", "--cached", "-U0", "--"] + files
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout


def post_incremental(code: str, diff: str):
    url = os.environ.get("REVIEW_URL", "http://127.0.0.1:8000/review_incremental")
    data = parse.urlencode({"code": code, "diff": diff}).encode()
    req = request.Request(url, data=data)
    with request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def main():
    files = get_staged_python_files()
    if not files:
        print("No staged Python files; skipping code review.")
        return 0

    diff = get_staged_diff_for(files)
    # Concatenate current staged file contents
    code_parts = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                code_parts.append(f"# File: {f}\n" + fh.read())
        except Exception:
            pass
    code = "\n\n".join(code_parts)

    try:
        result = post_incremental(code, diff)
    except Exception as e:
        print("[pre-commit] Review service not available:", e)
        return 0  # do not block commit if service is down

    findings = result.get('ai_feedback', [])
    if not findings:
        print("[pre-commit] No AI findings.")
        return 0

    print("[pre-commit] Findings:")
    block = False
    for fb in findings:
        it = fb.get('issue_type', 'general')
        line = fb.get('line_number', '-')
        desc = fb.get('description', '')
        effort = fb.get('effort_estimate', '')
        print(f"- {it} (line {line}) [{effort}]: {desc}")
        if it in {"bug", "security"}:
            block = True

    if block:
        print("[pre-commit] Blocking commit due to bug/security findings.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

