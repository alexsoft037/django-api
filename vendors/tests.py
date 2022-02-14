import datetime as dt
from decimal import Decimal
from unittest import mock

from celery.exceptions import Ignore
from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from guardian.shortcuts import assign_perm
from psycopg2.extras import DateTimeTZRange
from rest_framework.compat import coreapi
from rest_framework.exceptions import APIException

from accounts.models import Membership, Organization
from accounts.permissions import MANAGE_ORGANIZATION_PERMISSION
from listings.models import Property
from . import filters, models, serializers, tasks, views

User = get_user_model()


class JobTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="CO")
        inviter = User.objects.create(username="spam@example.org")
        cls.vendor_user = User.objects.create(
            username="egg@example.com",
            email="egg@example.com",
            first_name="Egg",
            last_name="Spam",
            phone="123456789",
        )
        Membership.objects.create(organization=cls.org, user=cls.vendor_user, is_default=True)
        Membership.objects.create(organization=cls.org, user=inviter, is_default=True)

        cls.vendor = models.Vendor.objects.create(
            user=cls.vendor_user,
            payout_preference=models.Vendor.Payments.Cash.value,
            invited_by=inviter,
        )
        cls.owner = User.objects.create(
            username="smallowner", first_name="test", last_name="test", is_superuser=True
        )
        Membership.objects.create(organization=cls.org, user=cls.owner, is_default=True)
        assign_perm(MANAGE_ORGANIZATION_PERMISSION, cls.owner, cls.org)
        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
            organization=cls.org,
        )

    def test_how_datetimerange_works(self):
        start_date = timezone.now()
        end_date = start_date + dt.timedelta(days=1)
        job = models.Job.objects.create(
            time_frame=DateTimeTZRange(start_date, end_date),
            base_cost=Decimal("10.00"),
            prop=self.prop,
            assignee=self.vendor,
        )
        self.assertEqual(job.time_frame.lower, start_date)
        self.assertEqual(job.time_frame.upper, end_date)


class JobFilterTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.filter = filters.JobFilter()
        organization = Organization.objects.create()
        cls.small_owner = User.objects.create(
            username="small.owner@example.com", account_type=User.AllowedTypes.Small_Owner.value
        )
        Membership.objects.create(organization=organization, user=cls.small_owner, is_default=True)
        assign_perm(MANAGE_ORGANIZATION_PERMISSION, cls.small_owner, organization)
        cls.cleaner1 = User.objects.create(
            username="cleaner@example.com", account_type=User.VendorTypes.Cleaner.value
        )

        cls.cleaner2 = User.objects.create(
            username="cleaner2@example.com", account_type=User.VendorTypes.Cleaner.value
        )

        spam_user = User.objects.create(username="spam@example.org")
        Membership.objects.create(organization=organization, user=spam_user, is_default=True)

        cls.vendor = models.Vendor.objects.create(
            invited_by=spam_user,
            payout_preference=models.Vendor.Payments.Cash.value,
            user=cls.cleaner1,
        )

        cls.vendor2 = models.Vendor.objects.create(
            invited_by=spam_user,
            payout_preference=models.Vendor.Payments.Cash.value,
            user=cls.cleaner2,
        )

        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
            organization=organization,
        )

        start_date = timezone.now()
        end_date = start_date + dt.timedelta(days=1)

        cls.job = models.Job.objects.create(
            time_frame=DateTimeTZRange(start_date, end_date),
            base_cost=Decimal("10.00"),
            prop=cls.prop,
            assignee=cls.vendor,
        )
        cls.job2 = models.Job.objects.create(
            time_frame=DateTimeTZRange(start_date, end_date),
            base_cost=Decimal("15.00"),
            prop=cls.prop,
            assignee=cls.vendor2,
        )

    def test_filter_queryset(self):
        view = None
        queryset = models.Job.objects.all()

        with self.subTest(msg="Jobs assigned to property"):
            request = mock.MagicMock(user=self.small_owner, query_params={})
            qs = self.filter.filter_queryset(request, queryset, view)
            self.assertEqual(qs.count(), 2)

        with self.subTest(msg="Jobs assigned to vendor1"):
            request = mock.MagicMock(user=self.cleaner1, query_params={})
            qs = self.filter.filter_queryset(request, queryset, view)
            self.assertEqual(qs.count(), 1)
            self.assertEqual(qs.first(), self.job)

        with self.subTest(msg="Jobs assigned to vendor2"):
            request = mock.MagicMock(user=self.cleaner2, query_params={})
            qs = self.filter.filter_queryset(request, queryset, view)
            self.assertEqual(qs.count(), 1)
            self.assertEqual(qs.first(), self.job2)

        queryset = mock.MagicMock()
        queryset.annotate.return_value = queryset

        with self.subTest("No filters"):
            request = mock.MagicMock()
            type(request.user).is_vendor = mock.PropertyMock(return_value=False)
            request.user.organization = None
            request.query_params = {}
            self.filter.filter_queryset(request, queryset, view)
            queryset.filter.assert_called_once_with(prop__organization=request.user.organization)

        with self.subTest("All filters"):
            request = mock.MagicMock()
            date = dt.date(2020, 10, 30)
            type(request.user).is_vendor = mock.PropertyMock(return_value=True)
            request.query_params = {
                "active": True,
                "address": "some address",
                "name": "some name",
                "date": date.isoformat(),
                "assignee": "123",
            }
            self.filter.filter_queryset(request, queryset, view)

            queryset.filter.assert_called_with(
                is_active=request.query_params["active"],
                full_address__icontains=request.query_params["address"],
                prop__name__icontains=request.query_params["name"],
                assignee__id=request.query_params["assignee"],
                assignee__user=request.user,
                date=date,
            )

        with self.subTest("Invalid date"):
            request = mock.MagicMock()
            type(request.user).is_vendor = mock.PropertyMock(return_value=True)
            request.query_params = {"date": "2019-15-32"}
            with self.assertRaises(APIException):
                self.filter.filter_queryset(request, queryset, view)

    def test_get_schema_fields(self):
        view = mock.MagicMock()
        fields = self.filter.get_schema_fields(view)
        self.assertEqual(len(fields), 7)

        for field in fields:
            self.assertIsInstance(field, coreapi.Field)


# Serializers tests


@mock.patch("vendors.signals.receiver")
class JobSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="CO")
        inviter = User.objects.create(username="spam@example.org")
        Membership.objects.create(organization=cls.organization, user=inviter, is_default=True)
        cls.vendor = models.Vendor.objects.create(
            user=User.objects.create(
                username="egg@example.com",
                email="egg@example.com",
                first_name="Egg",
                last_name="Spam",
                phone="123456789",
            ),
            payout_preference=models.Vendor.Payments.Cash.value,
            invited_by=inviter,
        )
        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
        )

    def test_validate_date(self, mock_receiver):
        start_date = timezone.now()
        end_date = start_date + dt.timedelta(days=1)

        all_bounds = ["[]", "()", "[)", "(]"]
        valid_bounds = "[]"

        ser = serializers.JobSerializer()

        for bounds in all_bounds:
            with self.subTest(bounds=bounds, message="Accept only inclusive bounds"):
                date_range = DateTimeTZRange(start_date, end_date, bounds)
                validated = ser.validate_date(date_range)
                self.assertEqual(validated._bounds, valid_bounds)

    def test_validate(self, mock_receiver):
        data = {
            "type": models.Job.Jobs.Repair.name,
            "time_frame": {"lower": "2018-01-10T12:00", "upper": "2018-01-16T11:00"},
            "base_cost": 10,
            "assignee_id": self.vendor.pk,
            "prop": self.prop.pk,
        }
        serializer = serializers.JobSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class ChecklistItemSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        org = Organization.objects.create(name="CO")
        inviter = User.objects.create(username="spam@example.org")
        Membership.objects.create(organization=org, user=inviter, is_default=True)

        vendor = models.Vendor.objects.create(
            user=User.objects.create(
                username="egg@example.com",
                email="egg@example.com",
                first_name="Egg",
                last_name="Spam",
                phone="123456789",
            ),
            payout_preference=models.Vendor.Payments.Cash.value,
            invited_by=inviter,
        )
        owner = User.objects.create(
            username="owner@example.com",
            email="owner@example.com",
            first_name="Owner",
            last_name="Spam",
            phone="+13335671000",
        )
        Membership.objects.create(organization=org, user=owner, is_default=True)
        assign_perm(MANAGE_ORGANIZATION_PERMISSION, owner, org)
        prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
            organization=org,
        )
        start_date = timezone.now()
        end_date = start_date + dt.timedelta(days=1)
        cls.job = models.Job.objects.create(
            time_frame=DateTimeTZRange(start_date, end_date, "[]"),
            job_type=models.Job.Jobs.Checkup.value,
            assignee=vendor,
            base_cost=Decimal("100.00"),
            prop=prop,
        )

    def test_create(self):
        ser = serializers.ChecklistItemSerializer()
        validated_data = {"name": "Some job", "job": self.job}

        with self.subTest(msg="Empty instruction"):
            instance = ser.create(validated_data)
            self.assertFalse(instance.instruction.all().exists())

        with self.subTest(msg="Non-empty instruction"):
            validated_data["instruction"] = [
                {"name": "Make a bed"},
                {"name": "Clean window", "done": True},
            ]
            instance = ser.create(validated_data)
            self.assertTrue(instance.instruction.all().exists())
            self.assertEqual(
                instance.instruction.filter(done=False).count(),
                1,
                "`done` should default to `False`",
            )
            self.assertEqual(instance.instruction.filter(done=True).count(), 1)


class VendorSerializerTestCase(TestCase):
    @mock.patch("vendors.serializers.VendorUserSerializer.create")
    def test_create(self, m_create):
        data = {"user": {"phone": "+12334567890", "account_type": User.VendorTypes.Cleaner.value}}

        ser = serializers.VendorSerializer(
            context={"request": mock.MagicMock(**{"user.organization": None})}
        )
        validated_data = ser.validate(data)
        self.assertTrue(validated_data["user"].has_unusable_password())
        self.assertIsNotNone(validated_data["user"].organization)

    # def test_update(self):
    #     phone = "1234567891"
    #     account_type = User.VendorTypes.Cleaner.value
    #     data = {"phone": phone, "account_type": "Cleaner"}
    #
    #     user = User.objects.create(username="vend", account_type=User.VendorTypes.Maintainer.value)  # noqa: E501
    #     instance = models.Vendor.objects.create(
    #         user=user, invited_by=user, payout_preference=models.Vendor.Payments.Cash.value
    #     )
    #     serializer = serializers.VendorSerializer(
    #         instance, context={"request": mock.MagicMock()}, data=data, partial=True
    #     )
    #     self.assertTrue(serializer.is_valid(), serializer.errors)
    #     serializer.save()
    #
    #     user.refresh_from_db()
    #
    #     self.assertEqual(phone, user.phone)
    #     self.assertEqual(account_type, user.account_type)


# Tasks tests


class CreateCleanJobsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        org = Organization.objects.create()
        inviter = User.objects.create(username="spam@example.org")
        Membership.objects.create(organization=org, user=inviter, is_default=True)

        cls.vendor = models.Vendor.objects.create(
            user=User.objects.create(
                username="egg@example.com",
                email="egg@example.com",
                first_name="Egg",
                last_name="Spam",
                phone="123456789",
            ),
            payout_preference=models.Vendor.Payments.Cash.value,
            invited_by=inviter,
        )
        owner = User.objects.create(
            username="owner@example.com",
            email="owner@example.com",
            first_name="Owner",
            last_name="Spam",
            phone="123456710",
        )
        Membership.objects.create(organization=org, user=owner, is_default=True)
        assign_perm(MANAGE_ORGANIZATION_PERMISSION, owner, org)
        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
            organization=org,
        )
        cls.prop.scheduling_assistant.automatically_assign = True
        cls.prop.scheduling_assistant.save()

        cls.date_has_job = dt.date.today()
        cls.date_no_job = dt.date.today() + dt.timedelta(days=1)

        models.Job.objects.create(
            job_type=models.Job.Jobs.Clean.value,
            base_cost=0,
            time_frame=DateTimeTZRange(
                dt.datetime.combine(cls.date_has_job, dt.datetime.min.time()),
                dt.datetime.combine(cls.date_has_job, dt.datetime.max.time()),
            ),
            prop=cls.prop,
            assignee_id=cls.vendor.id,
        )

    def test_create_clean_jobs(self):
        pass

    def test_create_clean_job(self):
        def check_job_exsits():
            return models.Job.objects.filter(
                prop_id=self.prop.id,
                time_frame__overlap=(self.date_no_job, self.date_no_job + dt.timedelta(days=1)),
            ).first()

        with self.subTest("Job already exists"), self.assertRaises(Ignore):
            tasks.create_clean_job(self.prop.id, self.date_has_job)

        with self.subTest("More then one job exists"), self.assertRaises(Ignore):
            models.Job.objects.create(
                job_type=models.Job.Jobs.Clean.value,
                base_cost=0,
                time_frame=DateTimeTZRange(
                    dt.datetime.combine(self.date_has_job, dt.datetime.min.time()),
                    dt.datetime.combine(self.date_has_job, dt.datetime.max.time()),
                ),
                prop=self.prop,
                assignee_id=self.vendor.id,
            )
            tasks.create_clean_job(self.prop.id, self.date_has_job)

        with self.subTest("No assignment"):
            self.assertIsNone(check_job_exsits())
            with self.assertRaises(Ignore):
                tasks.create_clean_job(self.prop.id, self.date_no_job)

        fee = 10
        models.Assignment.objects.create(
            prop=self.prop, vendor=self.vendor, order=1, cleaning_fee=fee
        )

        with self.subTest("Create new job"):
            self.assertIsNone(check_job_exsits())
            tasks.create_clean_job(self.prop.id, self.date_no_job)
            job = check_job_exsits()
            self.assertEqual(job.base_cost, fee)
            job.delete()

        with self.subTest("automatically_assign = False"):
            self.prop.scheduling_assistant.automatically_assign = False
            self.prop.scheduling_assistant.save()
            with self.assertRaises(Ignore):
                tasks.create_clean_job(self.prop.id, self.date_no_job)


# Views tests


class InstructionViewSetTestCase(TestCase):
    def test_perform_create(self):
        view = views.InstructionViewSet()

        m_serializer = mock.MagicMock(spec=serializers.InstructionSerializer)
        checklist_item_id = "some-id"
        with mock.patch.object(
            view, "get_parents_query_dict", return_value={"checklist_item_id": checklist_item_id}
        ) as m_parents:
            view.perform_create(m_serializer)
            m_parents.assert_called_once()
            m_serializer.save.assert_called_once_with(checklist_item_id=checklist_item_id)

    def test_filter_queryset_by_parents_lookups(self):
        queryset = mock.MagicMock(spec=models.Instruction.objects)
        view = views.InstructionViewSet()

        with self.subTest(msg="Parents ids"):
            parents = {"checklist_item_id": 2, "job_id": 1}

            with mock.patch.object(view, "get_parents_query_dict", return_value=parents.copy()):
                view.filter_queryset_by_parents_lookups(queryset)
                queryset.filter.assert_called_once_with(
                    checklist_item_id=parents["checklist_item_id"],
                    checklist_item__job_id=parents["job_id"],
                )

        with self.subTest(msg="No parents ids"):
            queryset.reset_mock()
            parents = {}

            with mock.patch.object(view, "get_parents_query_dict", return_value=parents.copy()):
                view.filter_queryset_by_parents_lookups(queryset)
                queryset.filter.assert_not_called()

        with self.subTest(msg="Invalid ids"):
            queryset.reset_mock()
            queryset.filter.side_effect = ValueError
            parents = {"job_id": 1.2, "checklist_item_id": True}

            with self.assertRaises(Http404), mock.patch.object(
                view, "get_parents_query_dict", return_value=parents.copy()
            ):
                view.filter_queryset_by_parents_lookups(queryset)
                queryset.filter.assert_called_once()


class ChecklistViewSetTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.view = views.ChecklistViewSet()

    def test_perform_create(self):
        m_serializer = mock.MagicMock(spec=serializers.ChecklistItemSerializer)
        checklist_item_id = "some-id"
        with mock.patch.object(
            self.view, "get_parents_query_dict", return_value={"checklist_item": checklist_item_id}
        ) as m_parents:
            self.view.perform_create(m_serializer)
            m_parents.assert_called_once()
            m_serializer.save.assert_called_once_with(checklist_item=checklist_item_id)


# class VendorViewSetTestCase(TestCase):
#     @mock.patch("vendors.views.models.Vendor.objects.filter")
#     def test_get_queryset(self, m_filter):
#         view = views.VendorViewSet()
#         view.request = mock.MagicMock()
#         view.get_queryset()
#         m_filter.assert_called_once_with(invited_by=view.request.user)
