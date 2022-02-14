from django.contrib import admin

from payments.models import CreditCard, Customer, PricingPlan, ProductTier, Subscription, Charge, \
    Dispute, Coupon

admin.site.register(CreditCard)
admin.site.register(Customer)
admin.site.register(PricingPlan)
admin.site.register(ProductTier)
admin.site.register(Subscription)
admin.site.register(Charge)
admin.site.register(Dispute)
admin.site.register(Coupon)
