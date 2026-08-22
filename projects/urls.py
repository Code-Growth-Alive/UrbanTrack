from django.urls import path

from .views import ProjectPublicDetailView

app_name = "projects"

urlpatterns = [
    path("projects/<int:pk>/", ProjectPublicDetailView.as_view(), name="detail"),
]
