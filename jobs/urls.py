"""Job board URLs."""

from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.JobListView.as_view(), name="list"),
    path("new/", views.job_create, name="create"),
    path("mine/", views.my_applications, name="my_applications"),
    path("<int:pk>/", views.JobPublicDetailView.as_view(), name="detail"),
    path("<int:pk>/apply/", views.job_apply, name="apply"),
    path("<int:pk>/manage/", views.job_manage, name="manage"),
]
