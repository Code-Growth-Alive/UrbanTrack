"""System admin dashboard URLs."""

from django.urls import path

from . import views

app_name = "adminpanel"

urlpatterns = [
    path("", views.admin_dashboard, name="dashboard"),
    path("users/", views.admin_user_list, name="user_list"),
    path("users/<int:pk>/edit/", views.admin_user_edit, name="user_edit"),
    path("users/<int:pk>/toggle/", views.admin_user_toggle_active, name="user_toggle"),
    path("users/<int:pk>/nominate/", views.admin_nominate_admin, name="user_nominate_admin"),
    path("users/<int:pk>/delete/", views.admin_user_delete, name="user_delete"),
    path("jobs/", views.admin_job_list, name="job_list"),
    path("projects/", views.admin_project_list, name="project_list"),
    path("applications/", views.admin_application_list, name="application_list"),
]
