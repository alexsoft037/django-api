import logging
import uuid

import dialogflow_v2 as dialogflow
from django.conf import settings

logger = logging.getLogger(__name__)


class DialogFlowService:
    def __init__(self, project_id=None, session_id=None, language_code="en"):
        self.client = dialogflow.SessionsClient()
        self.project_id = project_id or settings.DIALOGFLOW.get("PROJECT_ID", None)
        assert project_id is None, "Dialogflow project is null"
        self.session_id = session_id or str(uuid.uuid4())
        self.language_code = language_code

    def get_session(self):
        return self.client.session_path(self.project_id, self.session_id)

    def _get_text_query_input(self, message):
        text_input = dialogflow.types.TextInput(text=message, language_code=self.language_code)
        query_input = dialogflow.types.QueryInput(text=text_input)
        return query_input

    def detect_intent(self, message):
        query_input = self._get_text_query_input(message)
        response = self.client.detect_intent(session=self.get_session(), query_input=query_input)
        query_result = response.query_result
        intent_name = query_result.intent.display_name
        confidence = query_result.intent_detection_confidence
        parameters = query_result.parameters
        logger.debug("=" * 20)
        logger.debug(f"Query text: {response.query_result.query_text}")
        logger.debug(f"Detected intent: {intent_name} (confidence: {confidence})\n")
        logger.debug("Fulfillment text: {}\n".format(response.query_result.fulfillment_text))
        return intent_name, confidence, parameters
