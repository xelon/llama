from django.db import models


class SubscriberAccess(models.Model):
    email = models.EmailField(unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="")
    subscription_status = models.CharField(max_length=64, blank=True, default="")
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("email",)

    def __str__(self):
        return f"{self.email} ({self.subscription_status or 'none'})"
