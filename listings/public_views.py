from django.http import Http404
from rest_framework import mixins
from rest_framework.generics import GenericAPIView, get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Reservation
from .serializers import ReservationSerializer


class TokenBaseMixin:
    def get_object(self):
        request = self.request
        if not hasattr(request, "token_payload"):
            raise Http404
        queryset = self.filter_queryset(self.get_queryset())
        token_payload = request.token_payload
        return get_object_or_404(queryset, id=token_payload.get("id"))


class InquiryView(TokenBaseMixin, mixins.UpdateModelMixin, GenericAPIView):

    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
