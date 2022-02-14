from django.contrib.auth import get_user_model


DjangoUserModel = get_user_model()


def after_scenario(context, scenario):
    DjangoUserModel.objects.all().delete()
