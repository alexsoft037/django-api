# from unittest import TestCase, mock
#
# from send_mail.services import send_email
#
#
# FROM = "FROM"
# TO = "TO"
# TEXT = "TEXT"
# SUBJECT = "SUBJECT"
# ATTACHMENTS = list()
#
#
# class ServicesTestCase(TestCase):
#     @mock.patch("send_mail.services.EmailMultiAlternatives")
#     def test_send_email_called(self, email_mock):
#         send_email(
#             FROM,
#             TO,
#             TEXT,
#             SUBJECT,
#             ATTACHMENTS
#         )
#         email_mock.return_value.attach_alternatives.return_value =
#
#
# class SignalsTestCase(TestCase):
#     def test_send_email(self):
#         pass
