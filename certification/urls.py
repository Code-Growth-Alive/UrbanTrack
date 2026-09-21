from django.urls import path

from .views import (
    client_confirm,
    client_confirm_done,
    contribution_review,
    invitation_landing,
)

app_name = "certification"

urlpatterns = [
    path(
        "certification/invitations/<uuid:token>/",
        invitation_landing,
        name="invitation_landing",
    ),
    path(
        "certification/contributions/<int:pk>/review/",
        contribution_review,
        name="contribution_review",
    ),
    path(
        "certification/client-confirm/<uuid:token>/",
        client_confirm,
        name="client_confirm",
    ),
    path(
        "certification/client-confirm/done/",
        client_confirm_done,
        name="client_confirm_done",
    ),
]
