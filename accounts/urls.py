from django.urls import path

from .views import (
    ExpertListView,
    LogInView,
    LogOutView,
    PasswordChangeView,
    PublicExpertProfileView,
    SignUpView,
    account_settings,
    dashboard,
    expert_search,
    profile_edit,
    set_cv_template,
)

app_name = "accounts"

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("settings/", account_settings, name="settings"),
    path("settings/password/", PasswordChangeView.as_view(), name="password_change"),
    path("portfolio/edit/", profile_edit, name="profile_edit"),
    path("portfolio/cv-template/", set_cv_template, name="set_cv_template"),
    path("experts/", ExpertListView.as_view(), name="expert_list"),
    path("experts/search/", expert_search, name="expert_search"),
    path(
        "experts/<slug:professional_id>/",
        PublicExpertProfileView.as_view(),
        name="public_profile",
    ),
    path("login/", LogInView.as_view(), name="login"),
    path("logout/", LogOutView.as_view(), name="logout"),
    path("signup/", SignUpView.as_view(), name="signup"),
]
