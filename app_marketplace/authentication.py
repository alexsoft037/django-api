import re

import rsa
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class AirbnbAuthentication(BaseAuthentication):

    verifier = rsa.PublicKey.load_pkcs1_openssl_pem(
        b"-----BEGIN PUBLIC KEY-----\n"
        b"MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArEzC0MAU1MrmYjwwscW2\n"
        b"HbQgegnEbe6CZEroQ7nFMmOARdeiw7X9QOENQDe5pvK1o7tdYAvNpg5BRWTq90v+\n"
        b"UShZ4kqni1YaNXEZgeN7alR2m/KRP4lBRpVnBV11cVd7/lmLP3ux23AksDubh/Sj\n"
        b"CXkikx78pnof3itCLQqDAxBLCYPo3a4i54lniwDjeJS91Fto4c4ERr7CFD5EQih3\n"
        b"mC5z6zwPYpe53ZZTbFRMf1IG7QdhfiMoZQ7YAgMLZj8i9oJHuB4rV5zCNtJ7LNni\n"
        b"2hS20bGymsW93lhE1jtBx7RdTD1NCUGDOt3jOAjFEL2wGjNYiHictWdvpWR2v8Ym\n"
        b"owIDAQAB\n"
        b"-----END PUBLIC KEY-----"
    )

    def authenticate(self, request):
        payload = "{host}|{url}|{method}|{date}|{cont_type}|{body}".format(
            host=request.get_host().split(":")[0],
            url=request.path,
            method=request.method.upper(),
            date=request.META.get("HTTP_DATE", ""),
            cont_type=request.content_type,
            body=request.body.decode(),
        ).encode()

        try:
            match = re.match(
                r'signature\="(?P<signature>.*)"',
                next(
                    signature
                    for signature in request.META.get("HTTP_AUTHORIZATION", "").split(",")
                    if signature.startswith('signature="')
                ),
            )
            signature = match["signature"].encode()
        except (StopIteration, TypeError, IndexError):
            raise AuthenticationFailed("Missing signature")

        try:
            rsa.verify(payload, signature, self.verifier)
            return None, None
        except rsa.pkcs1.VerificationError:
            raise AuthenticationFailed("Invalid signature")
