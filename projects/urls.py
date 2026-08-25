from django.urls import path

from .views import (
    ProjectListView,
    ProjectPublicDetailView,
    project_create,
    project_manage,
)

app_name = "projects"

urlpatterns = [
    path("projects/", ProjectListView.as_view(), name="list"),
    path("projects/new/", project_create, name="create"),
    path("projects/<int:pk>/manage/", project_manage, name="manage"),
    path("projects/<int:pk>/", ProjectPublicDetailView.as_view(), name="detail"),
]
