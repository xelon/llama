from django.contrib import admin

from travel_assistant.models import SubscriberAccess


@admin.register(SubscriberAccess)
class SubscriberAccessAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "subscription_status",
        "stripe_customer_id",
        "stripe_subscription_id",
        "current_period_end",
        "created_at",
        "updated_at",
    )
    list_filter = ("subscription_status",)
    search_fields = ("email", "stripe_customer_id", "stripe_subscription_id")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
