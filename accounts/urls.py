from django.contrib.auth.views import (
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import path, reverse_lazy

from .forms import PasswordResetForm
from .views import (
    ConfirmEmailView,
    ExpertListView,
    LogInView,
    LogOutView,
    PasswordChangeView,
    PublicCompanyView,
    PublicExpertProfileView,
    SignUpView,
    account_settings,
    change_email,
    company_membership_action,
    correct_signup_email,
    dashboard,
    expert_search,
    profile_edit,
    resend_confirmation_code,
    set_cv_template,
    trust_score_methodology,
)

app_name = "accounts"

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("trust-score/", trust_score_methodology, name="trust_score"),
    path("settings/", account_settings, name="settings"),
    path(
        "settings/company/memberships/<int:pk>/",
        company_membership_action,
        name="company_membership_action",
    ),
    path("settings/password/", PasswordChangeView.as_view(), name="password_change"),
    path("settings/email/", change_email, name="change_email"),
    path("confirm-email/", ConfirmEmailView.as_view(), name="confirm_email"),
    path("confirm-email/resend/", resend_confirmation_code, name="resend_confirmation_code"),
    path("confirm-email/correct/", correct_signup_email, name="correct_signup_email"),
    path("portfolio/edit/", profile_edit, name="profile_edit"),
    path("portfolio/cv-template/", set_cv_template, name="set_cv_template"),
    path("experts/", ExpertListView.as_view(), name="expert_list"),
    path("experts/search/", expert_search, name="expert_search"),
    path(
        "experts/<slug:professional_id>/",
        PublicExpertProfileView.as_view(),
        name="public_profile",
    ),
    path("companies/<int:pk>/", PublicCompanyView.as_view(), name="company_public"),
    path("login/", LogInView.as_view(), name="login"),
    path("logout/", LogOutView.as_view(), name="logout"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path(
        "password-reset/",
        PasswordResetView.as_view(
            form_class=PasswordResetForm,
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.txt",
            html_email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        PasswordResetDoneView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
]
