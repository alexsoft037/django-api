from operator import itemgetter
from random import choice, randint
from uuid import uuid4

from locust import HttpLocust, TaskSet, task


class ReservationTasks(TaskSet):
    def on_start(self):
        self.client.headers.update(self.parent.client.headers)
        self._reservation_codes = []
        self.create_reservation()  # ensure there is at least one reservation

    @task(2)
    def get_reservation(self):
        try:
            confirmation_code = choice(self._reservation_codes)
        except IndexError:
            return

        self.client.get(
            f"/api/v1/reservations/{confirmation_code}/", name="/api/v1/reservations/[code]/"
        )

    @task(5)
    def create_reservation(self):
        try:
            property_id = choice(self.parent._property_ids)
        except IndexError:
            return

        data = {
            "startDate": "2018-08-01",
            "endDate": "2018-08-10",
            "status": "Accepted",
            "guestsAdults": randint(1, 2),
            "guestsChildren": randint(0, 3),
            "pets": randint(0, 1),
            "paid": randint(0, 1),
            "privateNotes": "Private Note",
            "rebookAllowedIfCancelled": bool(randint(0, 1)),
            "externalId": str(uuid4()),
            "connectionId": str(uuid4()),
            "prop": property_id,
            "guest": {
                "firstName": "John",
                "lastName": "Smith",
                "email": "john.smith@voyajoy.com",
                "secondaryEmail": "john.smith+1@voyajoy.com",
                "phone": "123456789",
                "secondaryPhone": "223456789",
                "avatar": "https://cdn.voyajoy.com/john-smith.jpg",
                "location": "Contact Location",
                "note": "Some Note",
            },
        }

        with self.client.post("/api/v1/reservations/", json=data, catch_response=True) as resp:
            try:
                self._reservation_codes.append(resp.json()["confirmationCode"])
            except KeyError:
                pass

    @task(1)
    def cancel_reservation(self):
        try:
            confirmation_code = choice(self._reservation_codes)
        except IndexError:
            return

        self.client.patch(f"/api/v1/reservations/{confirmation_code}/cancellation/")

    @task(5)
    def stop(self):
        self.interrupt()


class PublicAPITasks(TaskSet):

    tasks = {ReservationTasks: 10}

    _api_tokens = [
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjo3MywidXNlcm5hbWUiOiI3ZWE2ZTA5Mi00YWFiLTQwZWEtOTA5Ny0xN2MzNzExOWU3OGYiLCJleHAiOjE1MjE3MzA4OTgsImVtYWlsIjoiIn0.Vrb-2-x0I_0ao7AbU0T-2CDeOQJo_q-mOsa9lb5eSA8",  # noqa: E501
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjo3NCwidXNlcm5hbWUiOiIwM2Q1ZWEzYi1hZWE0LTQ2NTYtYWQxNC1hNmVhNDZhZGU3NDgiLCJleHAiOjE1MjE3MzEyNDIsImVtYWlsIjoiIn0.P25V1iSd4T7p1jE5thRBHL6VCCvujRJRF04uIHBKUyI",  # noqa: E501
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjo3NSwidXNlcm5hbWUiOiIzNTJmZTM5Yi1iZTAyLTRhYmMtYWJkNC03M2YxOTEwYWE5ZTIiLCJleHAiOjE1MjE3MzEyNDYsImVtYWlsIjoiIn0.2VhXSx3hD3BrFMdTXfsiirkB51JZaGN4X6KdkRYC5vM",  # noqa: E501
    ]

    def on_start(self):
        token = choice(self._api_tokens)
        self.client.headers.update({"Authorization": f"Token: {token}"})
        self._property_ids = []
        self.get_all_properties()  # populate self._property_ids

    @task(2)
    def get_all_properties(self):
        with self.client.get("/api/v1/properties/", catch_response=True) as resp:
            self._property_ids = list(map(itemgetter("id"), resp.json()))

    @task(1)
    def get_property(self):
        try:
            property_id = choice(self._property_ids)
        except IndexError:
            return

        self.client.get(f"/api/v1/properties/{property_id}/", name="/api/v1/properties/[id]/")


class PublicAPIUser(HttpLocust):
    task_set = PublicAPITasks
    min_wait = 1500
    max_wait = 3000
