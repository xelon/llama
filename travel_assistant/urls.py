from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/plan/preview/", views.plan_preview_api, name="plan_preview_api"),
    path("api/plan/pdf/", views.plan_pdf_api, name="plan_pdf_api"),
]
