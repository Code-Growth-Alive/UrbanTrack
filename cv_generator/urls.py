"""CV generator URLs."""

from django.urls import path

from . import views

app_name = "cv_generator"

urlpatterns = [
    path("", views.cv_builder, name="builder"),
    path("<str:skin>/", views.cv_preview, name="preview"),
    path("<str:skin>/pdf/", views.cv_pdf, name="pdf"),
    path("<str:skin>/docx/", views.cv_docx, name="docx"),
]
