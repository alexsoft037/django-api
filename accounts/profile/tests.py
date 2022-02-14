from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.serializers import ValidationError

from accounts.models import Organization
from .choices import Plan
from .models import PlanSettings, choose_plan
from .serializers import PlanSettingsSerializer

User = get_user_model()


class PlanSettingsSerializerTestCase(TestCase):
    def setUp(self):
        self.data = {"team": 1, "properties": 1, "plan": "some-plan"}

    @mock.patch("accounts.profile.serializers.choose_plan")
    def test_raise_on_wrong_plan(self, mock_choose):
        right_plan = self.data["plan"]
        self.data["plan"] = "wrong-plan"
        mock_choose.return_value = right_plan

        s = PlanSettingsSerializer()
        with self.assertRaises(ValidationError):
            s.validate(self.data)

        mock_choose.assert_called_once_with(self.data["team"], self.data["properties"])

    @mock.patch("accounts.profile.serializers.choose_plan")
    def test_plan_month_raise_error_if_value_less_than_0_or_bigger_than_366(self, mock_choose):
        right_plan = self.data["plan"]
        mock_choose.return_value = right_plan

        self.data["month_days"] = -10
        serializer = PlanSettingsSerializer(data=self.data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

        self.data["month_days"] = 367
        serializer = PlanSettingsSerializer(data=self.data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    @mock.patch("accounts.profile.serializers.choose_plan")
    def test_correct_plan(self, mock_choose):
        right_plan = self.data["plan"]
        mock_choose.return_value = right_plan

        s = PlanSettingsSerializer()
        validated = s.validate(self.data)
        self.assertNotIn("plan", validated)

        mock_choose.assert_called_once_with(self.data["team"], self.data["properties"])


class PlanSettingsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user = User.objects.create(username="user")
        cls.user.organization = Organization.objects.create()

    @classmethod
    def tearDownClass(cls):
        User.objects.all().delete()
        PlanSettings.objects.all().delete()

    @mock.patch("accounts.profile.models.choose_plan")
    def test_plan(self, mock_choose):
        plan = "some-plan"
        mock_choose.return_value = plan
        team = 1
        properties = 2

        o = PlanSettings.objects.create(
            team=team, properties=properties, organization=self.user.organization
        )
        self.assertEqual(plan, o.plan)
        self.assertEqual(o.month_days, 30)
        mock_choose.assert_called_once_with(team, properties)


class ChoosePlanTestCase(TestCase):
    def test_always_return_single(self):
        self.assertEqual(choose_plan(0, 0), Plan.SINGLE.value)
        self.assertEqual(choose_plan(1000, 1000), Plan.SINGLE.value)
