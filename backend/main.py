from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uuid
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from forecasting import run_prediction
from agent import run_agent
from report_generator import generate_report, report_to_html

app = FastAPI(title="Weatherly AI Weather Planning API")

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class WeatherRequest(BaseModel):
    lat: float
    lon: float
    startDate: str
    endDate: str
    activity: str
    variables: dict


class AgentChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ReportRequest(BaseModel):
    options: list[dict]
    activity: str
    explanation: str = ""
    intent: dict = {}


class EmailReportRequest(BaseModel):
    to_email: str
    options: list[dict]
    activity: str
    explanation: str = ""
    intent: dict = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict_weather(req: WeatherRequest):
    """Manual Mode: user picks the location/date/activity directly."""
    start_date = datetime.fromisoformat(req.startDate.replace("Z", "").replace("T", " "))
    end_date = datetime.fromisoformat(req.endDate.replace("Z", "").replace("T", " "))
    return run_prediction(req.lat, req.lon, start_date, end_date, req.activity)


@app.post("/agent/chat")
def agent_chat(req: AgentChatRequest):
    """AI Planning Agent: natural-language in, multi-step reasoning + tool use out.
    See agent.py for the planner/tools/decision-engine/memory implementation."""
    session_id = req.session_id or str(uuid.uuid4())
    result = run_agent(req.message, session_id)
    result["session_id"] = session_id
    return result


# Kept for backwards compatibility with the earlier single-shot /plan endpoint.
# New integrations should use /agent/chat.
@app.post("/plan")
def plan_legacy(req: AgentChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    result = run_agent(req.message, session_id)
    result["session_id"] = session_id
    return result


@app.post("/agent/report")
def generate_planning_report(req: ReportRequest):
    """Generate a structured planning report from agent results."""
    report = generate_report(
        options=req.options,
        intent=req.intent,
        activity=req.activity,
        explanation=req.explanation,
    )
    return report


@app.get("/agent/report/html", response_class=HTMLResponse)
def report_as_html(options_json: str = "", activity: str = "", explanation: str = ""):
    """Render an HTML version of the report (for direct browser download)."""
    import json
    try:
        options = json.loads(options_json) if options_json else []
    except Exception:
        options = []
    report = generate_report(options=options, intent={}, activity=activity, explanation=explanation)
    return report_to_html(report)


@app.post("/agent/email-report")
def email_report(req: EmailReportRequest):
    """
    Send the planning report to the specified email address.
    Requires SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS environment variables.
    Returns success/failure without raising — never claims success if sending fails.
    """
    report = generate_report(
        options=req.options,
        intent=req.intent,
        activity=req.activity,
        explanation=req.explanation,
    )
    html_body = report_to_html(report)
    text_body = report.get("markdown", report.get("summary", "See attached report."))

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if not smtp_host or not smtp_user:
        # No SMTP configured — return the report for client-side download instead
        return {
            "sent": False,
            "reason": "Email server not configured. Download the report instead.",
            "report": report,
        }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = report["title"]
        msg["From"] = smtp_user
        msg["To"] = req.to_email
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, req.to_email, msg.as_string())

        return {"sent": True, "to": req.to_email, "subject": report["title"]}
    except Exception as e:
        return {
            "sent": False,
            "reason": f"Email sending failed: {e}",
            "report": report,
        }
