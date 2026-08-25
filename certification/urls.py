from django.urls import path

from .views import contribution_review, invitation_landing

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
]
