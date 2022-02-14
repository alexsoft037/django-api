import datetime as dt

from rest_framework_jwt.settings import api_settings

jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER
jwt_decode_handler = api_settings.JWT_DECODE_HANDLER


def jwt_payload_no_expiry_handler(user):
    payload = jwt_payload_handler(user)
    payload["exp"] = dt.datetime(2100, 1, 1, 0, 0)
    return payload


def jwt_generate_token(type, id):
    return jwt_encode_handler(
        {"type": type, "id": id, "exp": dt.datetime.now() + dt.timedelta(days=3)}
    )
