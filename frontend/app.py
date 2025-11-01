from nicegui import ui
import requests
import json

BACKEND_URL = "http://localhost:8000/review"

ui.page_title('AI Code Review Assistant 🤖')

ui.markdown("## 🧠 AI Code Review Assistant")
ui.markdown("Paste your code below and get AI-driven feedback and auto-fix suggestions.")

# ---- Fixed UI definitions ----
code_area = ui.textarea(
    label='Paste your code here:',
    placeholder='def example():\n    pass',
    value='',
).style('width: 100%; height: 400px')

result_lint = ui.markdown("").classes('text-sm text-gray-500')
result_ai = ui.markdown("").classes('text-sm text-gray-500')
fixed_code_box = ui.textarea(
    label='Auto-fixed code:',
    value='',
).style('width: 100%; height: 400px')

# ---- Button handler ----
def run_review():
    code = code_area.value.strip()
    if not code:
        ui.notify("⚠️ Please paste some code first.", color='negative')
        return

    ui.notify("Reviewing code... please wait.", color='primary')
    try:
        res = requests.post(BACKEND_URL, data={"code": code})
        data = res.json()

        if data.get("lint_issues"):
            lint_md = "### 🧾 Lint Issues\n" + "\n".join([f"- {x}" for x in data["lint_issues"]])
        else:
            lint_md = "✅ No lint issues detected"
        result_lint.set_content(lint_md)

        feedbacks = data.get("ai_feedback", [])
        if feedbacks:
            ai_md = "### 💬 AI Suggestions\n"
            for fb in feedbacks:
                ai_md += f"**{fb.get('issue_type', 'general').title()}** (line {fb.get('line_number', '-')})\n\n"
                ai_md += f"{fb.get('description', '')}\n\n"
                if fb.get("suggested_fix"):
                    ai_md += f"```python\n{fb['suggested_fix']}\n```\n"
        else:
            ai_md = "✅ No AI feedback detected"
        result_ai.set_content(ai_md)

        fixed_code_box.value = data.get("fixed_code", "")
        ui.notify("✅ Review completed!", color='positive')

    except Exception as e:
        ui.notify(f"Error: {e}", color='negative')

ui.button("🚀 Run Review", on_click=run_review, color='primary').classes('mt-4')
ui.separator()
ui.label("Developed for Hackathon 2025 — AI-Powered Code Review Assistant").classes('text-xs text-gray-400 mt-6')

ui.run(title='AI Code Review Assistant', port=8502)
