"""
Notification channels for Dremio Lakehouse Monitor.
Supports email (SMTP) and webhook (Slack/Teams/PagerDuty/Discord).
"""

import json
import smtplib
import urllib.request
import urllib.error
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from lib import db

logger = logging.getLogger("dremio-monitor")

SEVERITY_EMOJI = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}
SEVERITY_COLOR = {"info": "#3b82f6", "warning": "#f59e0b", "critical": "#ef4444"}


class Notifier:
    """Sends alert notifications via configured channels."""

    def send_email(self, alert):
        config = db.get_notification_config("email")
        if not config or not config.get("enabled"):
            return
        cfg = config["config"]
        severity = alert.get("severity", "warning")
        subject = f"[{severity.upper()}] Dremio Monitor: {alert['message']}"
        body = self._format_email_body(alert)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg.get("from_addr", cfg.get("username", ""))
        msg["To"] = cfg.get("to_addr", "")
        msg.attach(MIMEText(body, "html"))

        try:
            port = int(cfg.get("port", 587))
            if cfg.get("use_ssl"):
                server = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=10)
            else:
                server = smtplib.SMTP(cfg["smtp_host"], port, timeout=10)
                server.starttls()
            if cfg.get("username"):
                server.login(cfg["username"], cfg.get("password", ""))
            server.sendmail(msg["From"], msg["To"].split(","), msg.as_string())
            server.quit()
            logger.info(f"Email sent: {subject}")
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            raise

    def send_webhook(self, alert):
        config = db.get_notification_config("webhook")
        if not config or not config.get("enabled"):
            return
        cfg = config["config"]
        url = cfg.get("url", "")
        if not url:
            return
        severity = alert.get("severity", "warning")
        emoji = SEVERITY_EMOJI.get(severity, "⚠️")
        payload = {
            "text": f"{emoji} *Dremio Monitor Alert*\n*{alert['message']}*",
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn",
                         "text": f"{emoji} *[{severity.upper()}] {alert['message']}*"}
            }]
        }
        if alert.get("details"):
            payload["blocks"].append({
                "type": "section",
                "text": {"type": "mrkdwn",
                         "text": f"```{json.dumps(alert['details'], indent=2)[:1500]}```"}
            })
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            logger.info(f"Webhook sent to {url}")
        except Exception as e:
            logger.error(f"Webhook failed: {e}")
            raise

    def send_test(self, channel):
        alert = {"message": "Test alert from Dremio Lakehouse Monitor",
                 "severity": "info", "details": {"test": True}}
        if channel == "email":
            self.send_email(alert)
        elif channel == "webhook":
            self.send_webhook(alert)
        return True

    def _format_email_body(self, alert):
        severity = alert.get("severity", "warning")
        color = SEVERITY_COLOR.get(severity, "#f59e0b")
        details_html = ""
        if alert.get("details"):
            details_html = f"<pre>{json.dumps(alert['details'], indent=2)}</pre>"
        return f"""
        <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto">
          <div style="background:{color};color:white;padding:16px;border-radius:8px 8px 0 0">
            <h2 style="margin:0">{SEVERITY_EMOJI.get(severity, '')} Dremio Lakehouse Monitor</h2>
          </div>
          <div style="background:#1a1a2e;color:#e0e0e0;padding:20px;border-radius:0 0 8px 8px">
            <p style="font-size:18px;margin-top:0"><strong>{alert['message']}</strong></p>
            {details_html}
            <hr style="border-color:#333">
            <p style="color:#888;font-size:12px">Severity: {severity.upper()} | Dremio Lakehouse Monitor</p>
          </div>
        </div>"""
