from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/plan/preview/", views.plan_preview_api, name="plan_preview_api"),
    path("api/plan/pdf/", views.plan_pdf_api, name="plan_pdf_api"),
    path("api/billing/create-checkout-session/", views.create_checkout_session_api, name="create_checkout_session_api"),
    path("api/billing/checkout/success/", views.checkout_success, name="checkout_success"),
    path("api/billing/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
