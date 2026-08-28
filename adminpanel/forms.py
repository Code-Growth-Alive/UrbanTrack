"""System administration forms: user management from the admin dashboard."""

from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import User

INPUT_CLASS = (
    "mt-1 block w-full rounded-md border border-charcoal-900/25 bg-white px-3 "
    "py-2 text-sm font-normal text-charcoal-900 shadow-none "
    "placeholder:font-normal placeholder:text-charcoal-300 "
    "focus:border-military-500 focus:outline-none focus:ring-2 "
    "focus:ring-military-300"
)

CHECKBOX_CLASS = "h-5 w-5 rounded border-charcoal-900/25"


class AdminUserForm(forms.ModelForm):
    """
    Edit a user's role, organisation and account status from the admin
    dashboard. Identity fields (email, professional ID) stay immutable.
    """

    password = forms.CharField(
        label=_("New password"),
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": INPUT_CLASS,
                "autocomplete": "new-password",
                "placeholder": _("Leave empty to keep the current password."),
            }
        ),
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "organisation_name",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
        )
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "organisation_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "role": forms.Select(attrs={"class": INPUT_CLASS + " appearance-none pr-9"}),
            "is_active": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
            "is_staff": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
            "is_superuser": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
        }
        help_texts = {
            "is_staff": _("Django admin panel access."),
            "is_superuser": _("Full administrative rights."),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
