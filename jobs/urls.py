"""Job board URLs."""

from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.JobListView.as_view(), name="list"),
    path("new/", views.job_create, name="create"),
    path("mine/", views.my_applications, name="my_applications"),
    path("my-jobs/", views.my_jobs, name="my_jobs"),
    path("<int:pk>/", views.JobPublicDetailView.as_view(), name="detail"),
    path("<int:pk>/apply/", views.job_apply, name="apply"),
    path("<int:pk>/manage/", views.job_manage, name="manage"),
    path("<int:pk>/edit/", views.job_update, name="update"),
    path("<int:pk>/delete/", views.job_delete, name="delete"),
    path(
        "applications/<int:pk>/edit/",
        views.application_update,
        name="application_update",
    ),
    path(
        "applications/<int:pk>/withdraw/",
        views.application_withdraw,
        name="application_withdraw",
    ),
]
