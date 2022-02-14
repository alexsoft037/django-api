from django.contrib import admin

from rental_network.models import Proxy, ProxyAssignment, Account, RentalNetworkJob, Screenshot

admin.site.register(Proxy)
admin.site.register(ProxyAssignment)
admin.site.register(Account)
admin.site.register(RentalNetworkJob)
admin.site.register(Screenshot)
