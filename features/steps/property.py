from behave import given, then, when
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Organization
from listings.models import Image, Property, Room

client = APIClient()

MINIMAL_JPG = (
    b"\xff\xd8\xff\xdb\x00C\x00\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03\x03\x03\x04"
    b"\x06\x04\x04\x04\x04\x04\x08\x06\x06\x05\x06\t\x08\n\n\t\x08\t\t\n\x0c\x0f\x0c\n\x0b\x0e"
    b"\x0b\t\t\r\x11\r\x0e\x0f\x10\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff"
    b"\xc9\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xcc\x00\x06\x00\x10\x10\x05\xff\xda"
    b"\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9"
)


@when("user create a new property")
def new_prop(context):
    context.prop_name = "Property"

    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.post("/properties/", data={"name": context.prop_name, "address": "Dream Street"})
    print(resp.status_code, resp.data)
    assert resp.status_code == status.HTTP_201_CREATED


@then("property is saved in a database")
def prop_saved(context):
    assert Property.objects.filter(name=context.prop_name).exclude(organization=None).count() == 1


@given("another user owns a property")
def other_prop(context):
    another = Organization.objects.create()
    prop = Property.objects.create(name="some property", property_type="xx", organization=another)
    assert prop.organization.pk == another.pk


@when("user lists all properties")
def all_props(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.get("/properties/")
    assert resp.status_code == status.HTTP_200_OK
    context.data = resp.data


@then("user can see only owned properties")
def only_own_properties(context):
    print(context.data)
    assert len(context.data["results"]) == 0
    del context.data


@given("user has a property")
def user_has_property(context):
    prop = Property.objects.create(
        name="House",
        property_type=Property.Types.Condo.value,
        rental_type=Property.Rentals.Shared.value,
        organization=context.user.organization,
    )
    context.prop_id = prop.pk


@when("user sends a new property image")
def add_prop_image(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    jpeg = SimpleUploadedFile("test_empty_file.jpg", MINIMAL_JPG, content_type="image/jpeg")

    resp = client.post(
        "/properties/{}/images/".format(context.prop_id), data={"url": jpeg}, format="multipart"
    )
    context.resp = resp.json()
    del context.prop_id
    assert resp.status_code == status.HTTP_201_CREATED


@then("property image is uploaded to a CDN")
def uploaded_to_cdn(context):
    assert "url" in context.resp
    assert context.resp["url"].startswith("https://")
    print(context.resp["url"])
    Image.url.field.storage.delete(context.resp["url"])


@given("user has a property with images")
def property_with_images(context):
    prop = Property.objects.create(
        name="Name",
        property_type=Property.Types.Apartment.value,
        rental_type=Property.Rentals.Private.value,
    )
    context.images = Image.objects.bulk_create(
        Image(url=url, prop_id=prop.pk, order=i)
        for i, url in enumerate(("http://example.org/1", "http://example.org/2"))
    )
    context.prop_id = prop.pk


@when("user changes properties images order")
def change_prop_image_order(context):
    new_order = [img.pk for img in reversed(context.images)]
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.post(
        "/properties/{}/images/order/".format(context.prop_id), data={"order": new_order}
    )

    assert resp.status_code == status.HTTP_200_OK

    del context.images
    context.new_order = new_order


@then("new properties images order is used")
def new_prop_images_order(context):
    resp = client.get("/properties/{}/images/".format(context.prop_id))
    print(resp.json())
    returned_order = [img["id"] for img in resp.json()]

    assert resp.status_code == status.HTTP_200_OK
    assert context.new_order == returned_order


@when("user updates property data")
def update_property(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.patch("/properties/{}/".format(context.prop_id), data={"floor": 1})
    assert resp.status_code == status.HTTP_200_OK
    context.patch_data = resp.json()


@then("responses gives data of a whole property")
def whole_property_after_update(context):
    get_resp = client.get("/properties/{}/".format(context.prop_id))
    assert context.patch_data == get_resp.json()
    del context.patch_data


@when("user sends a list of new rooms")
def try_bulk_create_rooms(context):
    should_be_removed = "Should be removed"
    Room.objects.create(
        room_type=Room.Types.Bedroom.value, description=should_be_removed, prop_id=context.prop_id
    )
    new_rooms = [
        {"type": "Bathroom", "description": "Some description"},
        {"type": "Bedroom", "description": "Other description"},
    ]
    context.new_rooms = new_rooms
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.put("/properties/{}/rooms/bulk/".format(context.prop_id), data=new_rooms)

    assert resp.status_code == status.HTTP_201_CREATED
    assert Room.objects.filter(prop_id=context.prop_id, description=should_be_removed).count() == 0


@then("new rooms are bulk create")
def bulk_created_rooms(context):
    room_count = Room.objects.filter(prop_id=context.prop_id).count()
    assert room_count == len(context.new_rooms)


@when("user lists all properties basic data")
def props_basic_data(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.get("/properties/?basic=true")
    assert resp.status_code == status.HTTP_200_OK
    context.data = resp.data


@then("user can see simplified response")
def props_basic_data_returned(context):
    print(context.data)
    assert len(context.data) > 0
    del context.data
