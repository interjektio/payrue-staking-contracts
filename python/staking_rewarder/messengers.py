import json
import requests
import datetime

from abc import ABC, abstractmethod


class Messenger(ABC):
    @abstractmethod
    def send_message(self, title, message, msg_type, **kwargs):
        pass


class SlackMessenger(Messenger):
    def __init__(
        self,
        webhook_url: str,
    ):
        self.webhook_url = webhook_url

    @staticmethod
    def message_type(msg_type: str):
        color = {"danger": "#f72d2d", "good": "#0ce838", "warning": "#f2c744"}
        return color[msg_type]

    def create_attachment_template(self, title, message, msg_type):
        color_code = self.message_type(msg_type)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        slack_report_at = "<!date^{timestamp}^{date} at {time}|{date_str}>".format(
            timestamp=int(now.timestamp()),
            date_str=now.strftime("%B %d, %Y %H:%M:%S"),
            date="{date}",
            time="{time}",
        )
        return [
            {
                "color": color_code,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{title}* ({slack_report_at})",
                        },
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"{message}"},
                    },
                ],
            }
        ]

    def send_message(self, title, message, msg_type, **kwargs):
        """
        notification_message: str
        attachments: list
        """
        data = {
            "text": f"{kwargs.get('notification_message', 'Notification')}",
        }
        attachments = self.create_attachment_template(title, message, msg_type)
        if not attachments:
            raise ValueError("No attachments provided")

        data["attachments"] = attachments

        response = requests.post(
            self.webhook_url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 200:
            raise ValueError(
                f"Request to Slack returned an error {response.status_code}, the response is:\n{response.text}"
            )
