from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueTogetherValidator

from cozmo_common.fields import ContextDefault
from . import models


class CreateCalendarMixin:
    def validate_url(self, url):
        self._cal = self.Meta.model(url=url)
        try:
            self._cal.fetch(commit=False)
        except ValueError as e:
            raise ValidationError(" ".join(e.args))

        return url

    def create(self, validated_data, **kwargs):
        return super().create({"data": self._cal.data, **validated_data})

    def update(self, instance, validated_data):
        if hasattr(self, "_cal"):
            instance.data = self._cal.data
        return super().update(instance, validated_data)


class LogSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SyncLog
        fields = ("date_added", "success", "events")


class CalendarColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CalendarColor
        fields = ("id", "name", "hex_color")


class ExternalCalendarSerializer(CreateCalendarMixin, serializers.ModelSerializer):

    cozmo_cal_id = serializers.HiddenField(default=ContextDefault("cozmo_cal_id"))
    logs = serializers.SerializerMethodField()
    color = serializers.SlugRelatedField(
        queryset=models.CalendarColor.objects.all(),
        slug_field="name",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = models.ExternalCalendar
        depth = 1
        fields = (
            "id",
            "name",
            "url",
            "date_updated",
            "date_added",
            "description",
            "events_count",
            "enabled",
            "cozmo_cal_id",
            "logs",
            "color",
        )
        validators = [
            UniqueTogetherValidator(
                queryset=models.ExternalCalendar.objects.all(), fields=("name", "cozmo_cal_id")
            )
        ]

    def get_logs(self, obj):
        latest_logs = obj.logs.all().order_by("-id")[:5]
        return LogSerializer(instance=latest_logs, many=True).data

    def create(self, validated_data, **kwargs):
        instance = super().create(validated_data, **kwargs)
        instance.cozmo_cal.refresh_ical(commit=True)
        models.SyncLog.objects.create(
            calendar=instance, success=True, events=instance.events_count
        )
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.cozmo_cal.refresh_ical(commit=True)
        return instance

    def to_representation(self, instance):
        color = instance.color
        ret = super().to_representation(instance)
        ret["color"] = CalendarColorSerializer(color).data
        return ret


class ExternalCalendarEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ExternalCalendarEvent
        exclude = ("hash", "external_cal")
        read_only_fields = ("uid", "summary", "start_date", "end_date", "stamp")


class CalendarSerializer(serializers.ModelSerializer):

    external_cals = ExternalCalendarSerializer(
        many=True, read_only=True, source="externalcalendar_set"
    )

    class Meta:
        model = models.CozmoCalendar
        fields = ("id", "prop", "external_cals")


class CheckCalendarSerializer(CreateCalendarMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CheckCalendar
        fields = ("url", "events", "events_count")
