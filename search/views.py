from collections import namedtuple

from django.conf import settings
from django.db import models
from django.db.models import CharField, Value
from django.db.models.functions import Concat
from rest_framework import generics, mixins, status
from rest_framework.response import Response

from accounts.models import OwnerUser
from accounts.permissions import GroupAccess
from cozmo_common.fields import AppendFields
from cozmo_common.filters import OrganizationFilter
from crm.models import Contact
from listings.filters import GroupAccessFilter
from listings.models import Property, Reservation
from owners.models import Owner
from search.filters import GenericSearchFilter
from search.serializers import GenericSearchSerializer
from send_mail.models import Message


class SearchView(mixins.RetrieveModelMixin, generics.GenericAPIView):
    permission_classes = (GroupAccess,)
    filter_backends = (OrganizationFilter, GenericSearchFilter, GroupAccessFilter)
    serializer_class = GenericSearchSerializer

    def get_object(self):
        GenericSearch = namedtuple(
            "GenericSearch",
            ["properties", "reservations", "conversation_threads", "contacts", "owners"],
        )
        query = self.request.query_params.get("q", "").strip()
        num_search_results = settings.MAX_GLOBAL_SEARCH_RESULTS
        properties = Property.objects.none()
        reservations = Reservation.objects.none()
        conversation_threads = Message.objects.none()
        contacts = Contact.objects.none()
        owners = OwnerUser.objects.none()
        if len(query) >= 3:
            properties = self.filter_queryset(
                Property.objects.annotate(
                    full_street=Concat(
                        "location__address",
                        Value(" "),
                        "location__apartment",
                        output_field=CharField(),
                    ),
                    full_owner_name=Concat(
                        "owner__user__first_name",
                        Value(" "),
                        "owner__user__last_name",
                        output_field=CharField(),
                    ),
                )
                .filter(
                    models.Q(name__icontains=query)
                    | models.Q(full_street__icontains=query)
                    | models.Q(full_owner_name__icontains=query)
                )
                .order_by("id")
            )[:num_search_results]

            # we do next thing because reservation do filter
            # through different organization lookup field
            # add after filtration we return it back to None
            with AppendFields(
                self,
                {"org_lookup_field": "prop__organization", "group_lookup_field": "prop__group"},
            ):
                reservations = self.filter_queryset(
                    Reservation.objects.annotate(
                        full_guest_name=Concat(
                            "guest__first_name",
                            Value(" "),
                            "guest__last_name",
                            output_field=CharField(),
                        ),
                        full_property_street=Concat(
                            "prop__location__address",
                            Value(" "),
                            "prop__location__apartment",
                            output_field=CharField(),
                        ),
                    )
                    .filter(
                        models.Q(guest__phone__icontains=query)
                        | models.Q(guest__email__icontains=query)
                        | models.Q(full_guest_name__icontains=query)
                        | models.Q(full_property_street__icontains=query)
                        | models.Q(confirmation_code=query)
                    )
                    .order_by("-end_date", "id")
                )[:num_search_results]

            # with AppendField(self, "org_lookup_field", "reservation__prop__organization"):
            #     conversation_threads = self.filter_queryset(
            #         Message.objects.filter(
            #             models.Q(sender__first_name__icontains=query)
            #             | models.Q(sender__last_name__icontains=query)
            #         ).order_by("conversation_id", "date")
            #     ).distinct()[:3]

            contacts = self.filter_queryset(
                Contact.objects.annotate(
                    full_contact_name=Concat(
                        "first_name", Value(" "), "last_name", output_field=CharField()
                    )
                ).filter(
                    models.Q(full_contact_name__icontains=query)
                    | models.Q(phone__icontains=query)
                    | models.Q(email__icontains=query)
                )
            )[:num_search_results]

            owners = Owner.objects.annotate(
                full_owner_name=Concat(
                    "user__first_name", Value(" "), "user__last_name", output_field=CharField()
                )
            ).filter(
                (
                    models.Q(full_owner_name__icontains=query)
                    | models.Q(user__email__icontains=query)
                    | models.Q(user__phone__icontains=query)
                ),
                organization=self.request.user.organization,
            )[
                :num_search_results
            ]
        return GenericSearch(properties, reservations, conversation_threads, contacts, owners)

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data, status=status.HTTP_200_OK)
