from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("billing/success/", views.billing_success_page, name="billing_success_page"),
    path("billing/portal/", views.billing_portal_redirect, name="billing_portal_redirect"),
    path("billing/restore/", views.billing_restore, name="billing_restore"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/plan/preview/", views.plan_preview_api, name="plan_preview_api"),
    path("api/plan/pdf/", views.plan_pdf_api, name="plan_pdf_api"),
    path("api/billing/request-restore-link/", views.request_restore_link_api, name="request_restore_link_api"),
    path("api/billing/create-checkout-session/", views.create_checkout_session_api, name="create_checkout_session_api"),
    path("api/billing/checkout/success/", views.checkout_success, name="checkout_success"),
    path("api/billing/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
