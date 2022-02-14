import datetime as dt
from unittest import mock
from unittest.mock import MagicMock
from uuid import uuid4

import jwt
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialLogin
from django.contrib.auth import get_user_model
from django.http.request import HttpRequest
from django.template import loader
from django.test import TestCase
from django.utils import timezone
from guardian.shortcuts import assign_perm
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_jwt.settings import api_settings

from accounts.choices import ApplicationTypes, RoleTypes
from accounts.signals import _get_perms, apply_user_permissions
from accounts.tasks import notify_trial_organisations
from notifications.models import Notification
from .adapter import SocialAccountAdapter
from .authentication import APITokenAuthentication, PublicJWTAuthentication
from .backends import PhoneAuthBackend
from .models import Membership, Organization, Token, User as CozmoUser
from .permissions import IsPublicApiUser, MANAGE_ORGANIZATION_PERMISSION, OrganizationPermissions
from .serializers import PhoneLoginSerializer, RegisterSerializer, UserDataSerializer
from .utils import jwt_decode_handler, jwt_generate_token

User = get_user_model()


class UserTestCase(TestCase):
    def test_is_django_user_model(self):
        self.assertEqual(User, CozmoUser)


class TokenTestCase(TestCase):
    def test_generate_key(self):
        token = Token(organization=Organization.objects.create())

        with self.subTest("User is created"):
            token.generate_key()
            self.assertIsInstance(token.user, User)
            self.assertEqual(token.user.account_type, User.SpecialTypes.Api_User.value)

        with self.subTest("User is not recreated"):
            user = token.user
            token.generate_key()
            self.assertIs(user, token.user)

        with self.subTest("Token should be valid for a looooong time"):
            jwt = jwt_decode_handler(token.generate_key())
            expiry_date = dt.datetime.fromtimestamp(jwt["exp"])
            now = dt.datetime.now()
            self.assertGreater(expiry_date, now.replace(year=now.year + 10))


class SocialAdapterTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = SocialAccountAdapter()
        cls.data = {"email": "mail@example.com", "username": "egg"}

    def setUp(self):
        self.sociallogin = SocialLogin()
        self.user = User(**self.data)
        self.sociallogin.user = self.user

    def tearDown(self):
        User.objects.all().delete()

    def test_populate_user_returns_new_user(self):
        user = self.adapter.populate_user(None, self.sociallogin, self.data)
        self.assertIsNone(user.pk)
        self.assertEqual(user.email, self.data["email"])

    def test_populate_user_returns_existing_user(self):
        self.user.save()
        user = self.adapter.populate_user(None, self.sociallogin, self.data)
        self.assertEqual(self.user.pk, user.pk)

    def test_save_user_creates_organization(self):
        self.user.save()

        with mock.patch(
            "accounts.adapter.DefaultSocialAccountAdapter.save_user", return_value=self.user
        ):
            request, sociallogin = mock.Mock(), mock.Mock()
            user = self.adapter.save_user(request, sociallogin)
            self.assertIsInstance(user.organization, Organization)
            self.assertTrue(user.has_perm(MANAGE_ORGANIZATION_PERMISSION, user.organization))


class RegisterSerializerTestCase(TestCase):
    def setUp(self):
        User.objects.all().delete()

    def test_validate_email(self):
        ser = RegisterSerializer()

        with self.subTest(msg="Non unique email"):
            email = "duplicate@example.org"
            User.objects.create(email=email)
            with self.assertRaises(ValidationError):
                ser.validate_email(email)

        with self.subTest(msg="Invalid email"):
            email = "invalid@"
            with self.assertRaises(ValidationError):
                ser.validate_email(email)

    def test_validate_incorrect_password(self):
        email = "email@example.org"
        data = {"email": email, "password": email}

        ser = RegisterSerializer()
        with self.assertRaises(ValidationError):
            ser.validate(data)


class PhoneLoginSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(
            phone="+48333222111", email="mail@example.com", username="egg"
        )
        cls.password = "abcd"
        cls.user.set_password(cls.password)
        cls.user.save()

    def test_validate_phone(self):
        por = PhoneLoginSerializer()

        with self.subTest(msg="Valid phone"):
            user = por._validate_phone(self.user.phone, self.password)
            self.assertEqual(self.user, user)

        with self.subTest(msg="Missing password"):
            with self.assertRaises(ValidationError):
                por._validate_phone(self.user.phone, None)

        with self.subTest(msg="Missing phone"):
            with self.assertRaises(ValidationError):
                por._validate_phone(None, self.password)

        with self.subTest(msg="Invalid phone"):
            invalid_phone = self.user.phone + "987"
            valid_user = por._validate_phone(invalid_phone, self.password)
            self.assertEqual(valid_user, None)

    def test_validate(self):
        por = PhoneLoginSerializer()

        with self.subTest(msg="Valid password"):
            attrs = por.validate({"phone": self.user.phone, "password": self.password})
            self.assertEqual(attrs["user"], self.user)

        with self.subTest(msg="Invalid password"), self.assertRaises(ValidationError):
            por.validate({"phone": self.user.phone, "password": "invalid password"})

        m_user = mock.MagicMock(is_active=False, spec=self.user)
        with mock.patch.object(por, "_validate_phone", return_value=m_user), (
            self.subTest(msg="Inactive user")
        ), self.assertRaises(ValidationError):
            self.user.is_active = False
            self.user.save()
            por.validate({"phone": self.user.phone, "password": self.password})


class UserDataSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.old_username = "anakin@example.org"
        cls.new_username = "vader@example.org"
        cls.user = User.objects.create(
            phone="+0333222111", email=cls.old_username, username=cls.old_username
        )

    def tearDown(self):
        self.user.username = self.old_username
        self.user.email = self.old_username
        self.user.save()

    def _test_not_change_username(self):
        serializer = UserDataSerializer(
            instance=self.user, data={"username": self.new_username}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        changed_user = serializer.save()
        self.assertEqual(changed_user.username, self.old_username)
        self.assertEqual(changed_user.email, self.old_username)
        self.assertTrue(
            changed_user.emailaddress_set.filter(verified=False, email=self.new_username).exists()
        )

    def test_no_emailaddress_instance(self):
        self._test_not_change_username()

    def test_with_emailaddress(self):
        email = EmailAddress.objects.create(user=self.user, email=self.old_username, verified=True)

        self._test_not_change_username()
        self.assertTrue(
            self.user.emailaddress_set.filter(email=self.new_username, verified=False).exists()
        )

        email.delete()


class PhoneAuthBackendTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(
            phone="+48333222111", email="mail@example.com", username="egg"
        )
        cls.user.set_password("abcd")
        cls.user.save()

    def test_authenticate(self):
        pab = PhoneAuthBackend()
        phone = "+48333222111"
        password = "abcd"

        with self.subTest(msg="Valid User"):
            user = pab.authenticate(None, username=phone, password=password)
            self.assertEqual(user, self.user)

        with self.subTest(masg="Invalid password"):
            user = pab.authenticate(None, username=phone, password="dcba")
            self.assertEqual(user, None)

        with self.subTest(masg="Invalid username"):
            user = pab.authenticate(None, username="+48333222112", password=password)
            self.assertEqual(user, None)

        with self.subTest(msg="No username specified"):
            kwargs = {"phone": phone}
            user = pab.authenticate(None, username=None, password=password, **kwargs)
            self.assertEqual(user, self.user)


class APITokenAuthenticationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.request = mock.MagicMock(spec=HttpRequest)
        cls.auth = APITokenAuthentication()

    def setUp(self):
        self.request.META = {}
        self.auth_header = "HTTP_AUTHORIZATION"

    def test_get_jwt_value(self):
        api_key = Token.objects.create(
            name="test api key", organization=Organization.objects.create()
        )
        self.request.META = {
            self.auth_header: "{} {}".format(self.auth.auth_header_prefix, api_key.key)
        }
        self.assertEqual(self.auth.get_jwt_value(self.request), api_key.key.encode())

    def test_get_jwt_value_invalid(self):
        with self.subTest("Missing authentication header"):
            self.request.META = {}
            self.assertIsNone(self.auth.get_jwt_value(self.request))

        with self.subTest("Invalid header value"):
            self.request.META = {
                self.auth_header: "{}{}".format(self.auth.auth_header_prefix, uuid4())
            }
            self.assertIsNone(self.auth.get_jwt_value(self.request), "Missing space after colon")

        with self.subTest("Invalid prefix name"):
            self.request.META = {self.auth_header: "{} {}".format("invalid", uuid4())}
            self.assertIsNone(self.auth.get_jwt_value(self.request))

        with self.subTest("Not existing token"):
            token = uuid4()
            self.assertFalse(Token.objects.filter(key=token).exists())
            self.request.META = {
                self.auth_header: "{} {}".format(self.auth.auth_header_prefix, token)
            }
            self.assertIsNone(self.auth.get_jwt_value(self.request))

    def test_authenticate_header(self):
        self.assertIsInstance(self.auth.authenticate_header(self.request), str)


class IsPublicApiUserTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.token = Token.objects.create(
            name="Test token", organization=Organization.objects.create()
        )

    def test_has_permission(self):
        with self.subTest("Valid Request User"):
            request = mock.MagicMock(user=self.token.user)
            resp = IsPublicApiUser().has_permission(request, mock.MagicMock())
            self.assertTrue(resp)

        with self.subTest("Invalid Request User"):
            user = User.objects.create(email="email@voyajoy.com")
            request = mock.MagicMock(user=user)
            resp = IsPublicApiUser().has_permission(request, mock.MagicMock())
            self.assertFalse(resp)

    @mock.patch("accounts.permissions.settings")
    def test_sandbox_production_tokens(self, settings):
        settings.DEBUG = False

        scenarios = {
            "Token and view sandbox": {
                "sandbox": True,
                "view": "tests.views_sandbox",
                "has_perm": True,
            },
            "Token and view production": {
                "sandbox": False,
                "view": "tests.views",
                "has_perm": True,
            },
            "Token sandbox, view production": {
                "sandbox": True,
                "view": "tests.views",
                "has_perm": False,
            },
            "Token production, view sandbox": {
                "sandbox": False,
                "view": "tests.views_sandbox",
                "has_perm": False,
            },
        }

        for test_name, spec in scenarios.items():
            with self.subTest(test_name):
                user = mock.MagicMock(
                    spec=User,
                    **{
                        "email": "email@voyajoy.com",
                        "is_api_user": True,
                        "token.is_sandbox": spec["sandbox"],
                    },
                )
                request = mock.MagicMock(user=user)
                view = mock.MagicMock(__module__=spec["view"])
                has_perm = IsPublicApiUser().has_permission(request, view)
                self.assertEqual(has_perm, spec["has_perm"])


class SignUpConfirmationTestCase(TestCase):

    template = "account/email/email_confirmation_signup_message.html"

    def test_renders_correctly(self):
        user = mock.Mock(email="activate.me@user.example.org")
        activate_url = "https://example.org/unique-activation-url/"
        context = {"user": user, "activate_url": activate_url}
        rendered = loader.get_template(self.template).render(context)
        self.assertIn(activate_url, rendered)
        self.assertIn(user.email, rendered)


class PublicJWTAuthenticationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.request = mock.MagicMock(spec=HttpRequest)
        cls.auth = PublicJWTAuthentication()

    def setUp(self):
        self.request.META = {}
        self.auth_header = "HTTP_AUTHORIZATION"

    def mock_request(self):
        return mock.MagicMock(
            spec=HttpRequest,
            META={
                self.auth_header: "{} {}".format(
                    api_settings.JWT_AUTH_HEADER_PREFIX, jwt_generate_token("Reservation", "1")
                )
            },
        )

    def test_authenticate(self):
        request = self.mock_request()
        self.auth.authenticate(request)
        self.assertTrue(hasattr(request, "token_payload"))

    @mock.patch("accounts.authentication.jwt_decode_handler")
    def test_authenticate_fail(self, m_jwt_decode):
        for exception in (jwt.ExpiredSignature, jwt.DecodeError, jwt.InvalidTokenError):
            with self.subTest("JWT raises", exception=exception):
                m_jwt_decode.side_effect = exception
                with self.assertRaises(AuthenticationFailed):
                    self.auth.authenticate(self.mock_request())


class TestTrialNotificationsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.now = timezone.now()

    def create_organization(self, date_created, name):
        organization = Organization.objects.create(
            name=name, applications=(ApplicationTypes.iCal_Magic.value,)
        )
        organization.date_created = date_created
        organization.save()
        return organization

    def create_user(self, organization, permition=MANAGE_ORGANIZATION_PERMISSION):
        username = organization.name + "_" + permition
        user = get_user_model().objects.create(
            username=username, email=f"{username}@mail.com", first_name="username"
        )
        Membership.objects.create(user=user, organization=organization, is_default=True)
        user.organization = organization
        assign_perm(permition, user, organization)

    def create_organizations(self, date_name_tuples):
        organizations = []
        for date, name in date_name_tuples:
            o = self.create_organization(date, name)
            self.create_user(o)
            self.create_user(o, OrganizationPermissions.admin.name)
            organizations.append(o)

        return organizations

    def test_notifications_without_organizations(self):
        notify_trial_organisations()
        self.assertEqual(0, Notification.objects.count())

    def test_notifications_with_organizations(self):
        organizations = self.create_organizations(
            (
                (self.now - dt.timedelta(days=3), "little"),
                (self.now - dt.timedelta(days=4), "start_trial"),
                (self.now - dt.timedelta(days=4), "start_trial2"),
                (self.now - dt.timedelta(days=7), "half_trial"),
                (self.now - dt.timedelta(days=12), "expiring_trial"),
                (self.now - dt.timedelta(days=12), "expiring_trial2"),
                (self.now - dt.timedelta(days=13), "old"),
            )
        )[1:-1]

        notify_trial_organisations()

        headers = [
            "Upcoming Cozmo (vacation rental property management system) features",
            "Upcoming Cozmo (vacation rental property management system) features",
            "You’re halfway through your iCal Magic 14-day FREE TRIAL!",
            "Your iCal Magic FREE TRIAL is about to expire",
            "Your iCal Magic FREE TRIAL is about to expire",
        ][::-1]

        notices = Notification.objects.order_by("object_id").all()

        self.assertEqual(5, notices.count())

        organizations.reverse()
        for notice in notices:
            organization = organizations.pop()
            header = headers.pop()
            self.assertEqual(organization, notice.content_object)
            self.assertTrue(header in notice.content)
            self.assertEqual(notice.to.email, organization.owner.email)
            self.assertEqual(
                f"{organization.name}_{MANAGE_ORGANIZATION_PERMISSION}", notice.to.username
            )


class PermissionsTestCase(TestCase):

    ROLE_PERMS = {
        "owner": {
            "TEST_APP_X": {
                "MODEL_X": ["view", "add", "change", "delete"],
                "MODEL_Y": ["change", "delete"],
            },
            "TEST_APP_Y": {
                "MODEL_A": ["view", "add", "change", "delete"],
                "MODEL_B": ["change", "delete"],
            },
        }
    }

    APP_PERMS = {"owner": {"TEST_APP_X": ["MODEL_Y"], "TEST_APP_Y": ["MODEL_A", "MODEL_B"]}}

    COMBINED_PERMS = {
        "TEST_APP_X": {"MODEL_X": ["view", "add", "change", "delete"]},
        "TEST_APP_Y": {},
    }

    OWNER_ADMIN_PERMS = {
        "vendors.view_worklog",
        "vendors.view_job",
        "settings.change_organizationsettings",
        "listings.view_group",
        "payments.add_subscription",
        "vendors.change_vendor",
        "vendors.change_assignment",
        "owners.change_owner",
        "automation.delete_reservationautomation",
        "vendors.view_vendor",
        "owners.delete_owner",
        "listings.view_reservationnote",
        "listings.view_property",
        "vendors.view_report",
        "accounts.change_organization",
        "accounts.delete_user",
        "vendors.change_job",
        "listings.delete_group",
        "send_mail.add_message",
        "payments.change_subscription",
        "listings.add_reservation",
        "payments.view_subscription",
        "listings.delete_property",
        "accounts.add_user",
        "listings.view_reservation",
        "accounts.change_user",
        "owners.add_owner",
        "listings.change_reservationnote",
        "listings.change_property",
        "settings.add_organizationsettings",
        "listings.change_group",
        "rental_connections.add_rentalconnection",
        "vendors.delete_vendor",
        "automation.change_reservationautomation",
        "owners.view_owner",
        "accounts.delete_organization",
        "rental_connections.delete_rentalconnection",
        "automation.add_reservationautomation",
        "listings.add_property",
        "listings.delete_reservation",
        "vendors.delete_assignment",
        "rental_connections.change_rentalconnection",
        "send_mail.view_message",
        "accounts.view_user",
        "vendors.view_assignment",
        "listings.add_reservationnote",
        "send_mail.view_conversation",
        "send_mail.add_conversation",
        "vendors.add_assignment",
        "settings.view_organizationsettings",
        "payments.delete_subscription",
        "rental_connections.view_rentalconnection",
        "send_mail.change_conversation",
        "listings.change_reservation",
        "automation.view_reservationautomation",
        "vendors.add_vendor",
        "listings.add_group",
        "vendors.add_job",
        "vendors.delete_job",
        "listings.delete_reservationnote",
        "send_mail.change_forwardingemail",
        "send_mail.add_forwardingemail",
        "send_mail.view_forwardingemail",
        "send_mail.delete_forwardingemail",
    }

    CONTRIBUTOR_PERMS = {
        "vendors.view_worklog",
        "vendors.view_job",
        "vendors.change_vendor",
        "vendors.change_assignment",
        "automation.delete_reservationautomation",
        "vendors.view_vendor",
        "listings.view_reservationnote",
        "listings.view_property",
        "vendors.view_report",
        "vendors.change_job",
        "send_mail.add_message",
        "listings.add_reservation",
        "listings.view_reservation",
        "listings.change_reservationnote",
        "listings.change_property",
        "vendors.delete_vendor",
        "automation.change_reservationautomation",
        "automation.add_reservationautomation",
        "listings.add_property",
        "listings.delete_reservation",
        "vendors.delete_assignment",
        "send_mail.view_message",
        "vendors.view_assignment",
        "listings.add_reservationnote",
        "send_mail.view_conversation",
        "send_mail.add_conversation",
        "vendors.add_assignment",
        "send_mail.change_conversation",
        "listings.change_reservation",
        "automation.view_reservationautomation",
        "vendors.add_vendor",
        "vendors.add_job",
        "vendors.delete_job",
        "listings.delete_reservationnote",
    }

    @classmethod
    def setUpTestData(cls):
        cls.apps = [ApplicationTypes.Owners.value, ApplicationTypes.Vendors.value]

    def create_user_and_apply_perms(self, role):
        user = get_user_model().objects.create(
            username="NAME", first_name="FOO", last_name="BAR", role=role
        )
        with mock.patch.object(user, "organization", MagicMock(applications=self.apps)):
            apply_user_permissions(user.__class__, user)
        return user

    @mock.patch("accounts.signals.settings.USER_ROLES", ROLE_PERMS)
    @mock.patch("accounts.signals.settings.APP_USER_PERMS", APP_PERMS)
    def test_get_perms(self):
        """
        Tests if the list of permissions are properly generated and missing apps permissions
        are removed
        """
        perms = _get_perms(RoleTypes.owner.value, [ApplicationTypes.Vendors.value])
        self.assertDictEqual(perms, self.COMBINED_PERMS)

    def test_apply_perms_owner(self):
        user = self.create_user_and_apply_perms(role=RoleTypes.owner.value)
        perms = user.get_all_permissions()
        self.assertEqual(perms, self.OWNER_ADMIN_PERMS)

    def test_apply_perms_admin(self):
        user = self.create_user_and_apply_perms(role=RoleTypes.admin.value)
        perms = user.get_all_permissions()
        self.assertFalse("accounts.delete_organization" in perms)

    def test_apply_perms_contributor(self):
        user = self.create_user_and_apply_perms(role=RoleTypes.contributor.value)
        perms = user.get_all_permissions()
        self.assertEqual(perms, self.CONTRIBUTOR_PERMS)
