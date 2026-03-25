import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List

try:
    from linebot.v3.messaging import (
        Configuration,
        ApiClient,
        MessagingApi,
        PushMessageRequest,
        TextMessage
    )
    LINE_SDK_AVAILABLE = True
except ImportError:
    LINE_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

class LineNotifier:
    """
    A class to send notifications via LINE Messaging API (v3).
    """
    def __init__(self, access_token: Optional[str] = None, user_id: Optional[str] = None):
        self.access_token = access_token or os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
        self.user_id = user_id or os.environ.get('LINE_USER_ID')

    def send_summary(self, message: str) -> bool:
        if not LINE_SDK_AVAILABLE:
            logger.warning("line-bot-sdk not installed. Cannot send LINE notification.")
            return False

        if not self.access_token or not self.user_id:
            logger.warning("LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID not set. Skipping notification.")
            return False
            
        if not message:
            logger.warning("Empty message provided to LineNotifier.send_summary.")
            return False

        configuration = Configuration(access_token=self.access_token)
        
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                text_message = TextMessage(text=message)
                push_message_request = PushMessageRequest(
                    to=self.user_id,
                    messages=[text_message]
                )
                line_bot_api.push_message(push_message_request)
                logger.info("LINE notification sent successfully.")
                return True
        except Exception as e:
            logger.error(f"Failed to send LINE notification: {e}")
            return False

class EmailNotifier:
    """
    A class to send notifications via Email (SMTP).
    Supports multiple recipients via comma-separated string.
    """
    def __init__(
        self, 
        smtp_server: Optional[str] = None, 
        smtp_port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        recipient: Optional[str] = None
    ):
        self.smtp_server = smtp_server or os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.environ.get('SMTP_PORT', '587'))
        self.username = username or os.environ.get('SMTP_USERNAME')
        self.password = password or os.environ.get('SMTP_PASSWORD')
        # recipient can be "mail1@example.com, mail2@example.com"
        self.recipient_str = recipient or os.environ.get('SMTP_RECIPIENT', 'mylin102@gmail.com')

    def _get_recipient_list(self) -> List[str]:
        if not self.recipient_str:
            return []
        return [r.strip() for r in self.recipient_str.split(',') if r.strip()]

    def send_email(self, subject: str, body: str) -> bool:
        """
        Send an email notification. Automatically formats Markdown-like tables 
        into styled HTML for better display.
        """
        recipients = self._get_recipient_list()
        if not all([self.username, self.password]) or not recipients:
            logger.warning("Email credentials or recipients not set. Skipping email.")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.username
            msg['To'] = self.username
            msg['Subject'] = subject

            # Basic HTML styling for tables and fonts
            html_body = f"""
            <html>
            <head>
            <style>
                body {{ font-family: sans-serif; line-height: 1.6; color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f4f4f4; font-weight: bold; }}
                tr:nth-child(even) {{ background-color: #fafafa; }}
                .buy {{ color: #d32f2f; font-weight: bold; }}
                .sell {{ color: #388e3c; font-weight: bold; }}
                h2 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; margin-top: 30px; }}
            </style>
            </head>
            <body>
                {self._markdown_to_basic_html(body)}
            </body>
            </html>
            """

            msg.attach(MIMEText(html_body, 'html'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.username, recipients, msg.as_string())
            server.quit()
            
            logger.info(f"Email sent successfully to {len(recipients)} recipient(s).")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def _markdown_to_basic_html(self, text: str) -> str:
        """
        Extremely simple converter for the specific Markdown generated by this tool.
        Converts headers, bold text, and Markdown tables to HTML.
        """
        import re
        lines = text.split('\n')
        html_lines = []
        in_table = False
        table_rows = []

        for line in lines:
            line = line.strip()
            
            # Handle Headers
            if line.startswith('## '):
                if in_table: html_lines.append(self._format_table(table_rows)); in_table = False; table_rows = []
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith('# '):
                if in_table: html_lines.append(self._format_table(table_rows)); in_table = False; table_rows = []
                html_lines.append(f"<h1>{line[2:]}</h1>")
            
            # Handle Tables
            elif line.startswith('|'):
                if '---' in line:
                    continue
                in_table = True
                table_rows.append(line)
            
            # Handle standard text and Bold
            else:
                if in_table:
                    html_lines.append(self._format_table(table_rows))
                    in_table = False
                    table_rows = []
                
                if line:
                    # Bold **text** -> <b>text</b>
                    line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
                    html_lines.append(f"<p>{line}</p>")
                else:
                    html_lines.append("<br>")

        if in_table:
            html_lines.append(self._format_table(table_rows))

        return "".join(html_lines)

    def _format_table(self, rows: List[str]) -> str:
        if not rows: return ""
        html = ["<table>"]
        for i, row in enumerate(rows):
            cells = [c.strip() for c in row.split('|') if c.strip()]
            tag = "th" if i == 0 else "td"
            html.append("<tr>")
            for cell in cells:
                # Handle bold in cells
                import re
                cell = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', cell)
                html.append(f"<{tag}>{cell}</{tag}>")
            html.append("</tr>")
        html.append("</table>")
        return "".join(html)
