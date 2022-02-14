from unittest import mock

from django.test import TestCase

from services.dialogflow import DialogFlowService

MESSAGE = "MESSAGE"
INTENT_NAME = "NAME"
CONFIDENCE = "0.000000"
PARAMETERS = {}
SESSION_ID = "SESSION_ID"


@mock.patch("services.dialogflow.uuid", return_value=mock.MagicMock())
@mock.patch("services.dialogflow.settings", return_value=mock.MagicMock())
@mock.patch("services.dialogflow.dialogflow", return_value=mock.MagicMock())
class DialogFlowServiceTest(TestCase):
    def _get_service(self):
        return DialogFlowService()

    def test_result_expected(self, dialog_mock, settings_mock, uuid_mock):
        """
        Tests for expected result
        """

        uuid_mock.uuid4.return_value = SESSION_ID
        query_result_mock = mock.MagicMock()
        query_result_mock.intent.display_name = INTENT_NAME
        query_result_mock.intent_detection_confidence = CONFIDENCE
        query_result_mock.parameters = PARAMETERS
        dialog_mock.SessionsClient.return_value.detect_intent.return_value.query_result = (
            query_result_mock
        )
        service = self._get_service()
        self.assertEquals(service.session_id, SESSION_ID)
        self.assertEquals(service.language_code, "en")
        with mock.patch.object(service, "_get_text_query_input") as input_mock:
            name, confidence, parameters = service.detect_intent(MESSAGE)
            self.assertEquals(name, INTENT_NAME)
            self.assertEquals(confidence, CONFIDENCE)
            self.assertEquals(parameters, PARAMETERS)
            input_mock.assert_called_with(MESSAGE)
