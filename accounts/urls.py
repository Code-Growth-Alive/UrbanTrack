from django.urls import path

from .views import PublicExpertProfileView

app_name = "accounts"

urlpatterns = [
    path(
        "experts/<slug:professional_id>/",
        PublicExpertProfileView.as_view(),
        name="public_profile",
    ),
]
