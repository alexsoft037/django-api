from django.test import TestCase

from automation.serializers import ReservationAutomationSerializer


class ReservationAutomationTest(TestCase):
    def _get_serializer(self, data):
        return ReservationAutomationSerializer(data=data, context={"organization": {}})

    def test_serializer_valid(self):
        data = {
            "days_delta": -1,
            "event": 1,
            "time": "12:00",
            "method": 1,
            "recipient_type": 2,
            "recipient_address": "test@voyajoy.com",
            "cc_address": ["cc1@voyajoy.com", "cc2@voyajoy.com"],
            "template_id": 1,
        }
        serializer = self._get_serializer(data)
        valid = serializer.is_valid()
        self.assertTrue(valid)

    def test_serializer_email_type(self):
        data = {
            "days_delta": -1,
            "event": 1,
            "time": "12:00",
            "method": 1,
            "recipient_type": 2,
            "cc_address": ["cc1@voyajoy.com", "cc2@voyajoy.com"],
            "template_id": 1,
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())

    # def test_view(self):
    #     request_mock = mock.Mock()
    #     request_mock.return_value.data = {}
    #
    #     view = ReservationAutomationViewSet(request=request_mock, format_kwarg=None)
    #     response = view.create(request=request_mock)
    #     self.assertEquals(response.status_code, status.HTTP_201_CREATED)
    # with mock.patch.object(
    #     view, "get_serializer_class", return_value=ReservationAutomationSerializer
    # ):
    #     serializer = view.get_serializer()
    #     self.assertFalse(hasattr(serializer, "skip_ipa_validation"))


HEADLINE = "HEADLINE"


class AutomationTaskTest(TestCase):
    """
    Test ReservationMessage is created
    * ReservationMessage created
    * EMail Message is created
    * Not created
    """

    @classmethod
    def setUpTestData(self):
        # self.organization = Organization.objects.create()
        # self.prop = Property.objects.create(
        #     name="some property",
        #     rental_type=Property.Rentals.Entire_Home.value,
        #     property_type=Property.Types.Condo.value,
        #     organization=self.organization
        # )
        # self.guest = Contact.objects.create(
        #     first_name="FIRST",
        #     last_name="LAST",
        #     email="EMAIL",
        #     organization=self.organization
        # )
        # self.reservation = Reservation.objects.create(
        #     start_date="2019-01-01",
        #     end_date="2019-01-02",
        #     prop=self.prop
        # )
        # self.template = Template.objects.create(
        #     headline=HEADLINE,
        #     organization=self.organization,
        #     prop=self.prop
        # )
        # self.schedule = ReservationAutomation.objects.create(
        #     days_delta=1,
        #     event=1,
        #     time="10:00",
        #     method=1,
        #     recipient_type=1,
        #     recipient_address="test@voyajoy.com",
        #     cc_address=["cc@cc.com"],
        #     bcc_address=["bcc@bcc.com"],
        #     template=self.template
        # )
        pass

    # def test_render_template(self):
    # reservation = mock.Mock(return_value)
    # template = mock.Mock()
    # render_template
