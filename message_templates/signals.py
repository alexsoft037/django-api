DEFAULT_TEMPLATE = "welcome"

# commented thsi out as it may not be relevant with recent changes
# @receiver(post_save, sender=Property)
# def create_welcome_template(sender, **kwargs):
#     created = kwargs["created"]
#     if created:
#         instance = kwargs["instance"]
#         WelcomeTemplate.objects.create(
#             prop=instance,
#             name="Welcome letter",
#             description="Sent prior to check-out",
#             organization=instance.organization,
#             template=DEFAULT_TEMPLATE,
#         )
