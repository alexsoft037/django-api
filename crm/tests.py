from unittest import mock

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from accounts.models import Organization
from . import fields, models, serializers, views


# fields tests


class TagRelatedFieldTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.field = fields.TagRelatedField()
        cls.name = "tag name"

    def test_to_representation(self):
        with self.subTest(msg="Value is Tag instance"):
            tag = models.Tag(name=self.name)
            value = self.field.to_representation(tag)
            self.assertEqual(value, self.name)

        with self.subTest(msg="Value is not Tag instance"):
            not_tag = mock.Mock(name=self.name)
            with self.assertRaises(ValueError):
                self.field.to_representation(not_tag)

    def test_to_internal_value(self):
        tag = self.field.to_internal_value(self.name)
        self.assertIsInstance(tag, models.Tag)
        self.assertEqual(tag.name, self.name)
        self.assertIsNone(tag.id)


# serializers tests


class TickerSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.title = "Some title"
        cls.tags = ["tag", "other"]
        cls.organization = Organization.objects.create()
        cls.context = {"request": mock.Mock(**{"user.organization": cls.organization})}

    def test_validate_assignee(self):
        serializer = serializers.TicketDetailedSerializer(context=self.context)

        with self.subTest(msg="Assignee is None"):
            assignee = None
            ret_assignee = serializer.validate_assignee(assignee)
            self.assertIs(assignee, ret_assignee)

        with self.subTest(msg="Organization is same as user's"):
            assignee = mock.Mock(organization=self.organization)
            ret_assignee = serializer.validate_assignee(assignee)
            self.assertIs(assignee, ret_assignee)

        with self.subTest(msg="Organization is different then user's"):
            other_organization_id = self.organization.id + 1
            self.assertNotEqual(self.organization.id, other_organization_id)
            assignee = mock.Mock(organization_id=other_organization_id)

            with self.assertRaises(ValidationError):
                serializer.validate_assignee(assignee)

        with self.subTest(msg="Assignee is not in organization"):
            assignee = mock.Mock(organization_id=None)

            with self.assertRaises(ValidationError):
                serializer.validate_assignee(assignee)

    def test_create(self):
        serializer = serializers.TicketDetailedSerializer(
            data={
                "title": self.title,
                "tags": self.tags,
                "type": models.Ticket.TicketTypes.Task.name,
            },
            context=self.context,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save(organization=self.organization)
        self.assertIsInstance(instance, models.Ticket)
        self.assertCountEqual(instance.tags.values_list("name", flat=True), self.tags)
        self.assertEqual(instance.ticketevent_set.count(), 1)
        self.assertEqual(instance.ticketevent_set.first().diff[0], "created")

    def test_update(self):
        old_type = models.Ticket.TicketTypes.Problem
        new_type = models.Ticket.TicketTypes.Question

        ticket = models.Ticket.objects.create(
            title=self.title, organization=self.organization, ticket_type=old_type
        )
        self.assertEqual(ticket.tags.count(), 0)
        self.assertEqual(ticket.ticket_type, old_type)

        with self.subTest(msg="Add new values, change other"):
            serializer = serializers.TicketDetailedSerializer(
                instance=ticket,
                partial=True,
                data={"tags": self.tags, "type": models.Ticket.TicketTypes.Question.name},
            )

            self.assertTrue(serializer.is_valid(), serializer.errors)
            instance = serializer.save()
            self.assertCountEqual(instance.tags.values_list("name", flat=True), self.tags)
            self.assertEqual(instance.ticketevent_set.count(), 2)
            event1, event2 = instance.ticketevent_set.all()
            events_map = {
                "add": ["add", "tags", [[i, t] for i, t in enumerate(self.tags)]],
                "change": ["change", "type", [old_type.name, new_type.name]],
            }
            self.assertListEqual(event1.diff, events_map.pop(event1.diff[0]))
            self.assertListEqual(event2.diff, events_map.pop(event2.diff[0]))
            self.assertDictEqual(events_map, {}, msg="Both events should occur")

        with self.subTest(msg="Leave tags when field not present"):
            serializer = serializers.TicketDetailedSerializer(
                instance=ticket, partial=True, data={"title": "Some new title"}
            )

            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertCountEqual(instance.tags.values_list("name", flat=True), self.tags)
            instance = serializer.save()
            self.assertCountEqual(instance.tags.values_list("name", flat=True), self.tags)

        with self.subTest(msg="Remove all tags"):
            serializer = serializers.TicketDetailedSerializer(
                instance=ticket, partial=True, data={"tags": []}
            )

            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertCountEqual(instance.tags.values_list("name", flat=True), self.tags)
            instance = serializer.save()
            self.assertEqual(instance.tags.count(), 0)


# views tests


class MessageViewSetTestCase(TestCase):
    def test_perform_create(self):
        request = mock.MagicMock(user="some user")
        view = views.MessageViewSet(request=request)
        serializer = mock.MagicMock(spec=views.MessageViewSet.serializer_class)
        view.perform_create(serializer)
        serializer.save.assert_called_once_with(author=request.user)


class TicketViewSetTestCase(TestCase):
    def test_perform_create(self):
        request = mock.MagicMock()
        view = views.TicketViewSet(request=request)
        serializer = mock.MagicMock(spec=views.TicketViewSet.serializer_class)
        view.perform_create(serializer)
        serializer.save.assert_called_once_with(
            organization=request.user.organization, creator=request.user
        )
