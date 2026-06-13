from django.contrib import admin
from .models import FXRate

@admin.register(FXRate)
class FXRateAdmin(admin.ModelAdmin):
    """
    Admin registration for core FXRate model.
    
    Why: Allows admins to configure exchange conversion rates between currencies.
    """
    list_display = ('id', 'from_currency', 'to_currency', 'rate', 'effective_date')
    search_fields = ('from_currency', 'to_currency')
    list_filter = ('effective_date',)
