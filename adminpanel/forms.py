"""System administration forms: user management from the admin dashboard."""

from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import Role, User

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
    Edit a user's details, account status and company from the admin dashboard.
    Identity fields (email, professional ID) stay immutable.

    Only the single Django superuser can promote a user to the ``admin`` role:
    admins may edit other accounts but cannot nominate new admins.
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
            "company",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
        )
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "company": forms.Select(attrs={"class": INPUT_CLASS + " appearance-none pr-9"}),
            "role": forms.Select(attrs={"class": INPUT_CLASS + " appearance-none pr-9"}),
            "is_active": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
            "is_staff": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
            "is_superuser": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
        }
        help_texts = {
            "is_staff": _("Django admin panel access."),
            "is_superuser": _("Full administrative rights (only for the platform owner)."),
        }

    def __init__(self, *args, acting_user=None, **kwargs):
        self.acting_user = acting_user
        super().__init__(*args, **kwargs)
        role_choices = list(Role.choices)
        if not getattr(acting_user, "is_superuser", False):
            # Non-superusers (admins) cannot manage role elevation at all.
            role_choices = [(value, label) for value, label in role_choices if value != Role.ADMIN]
            self.fields["role"].disabled = True
            self.fields["role"].help_text = _(
                "Only the platform superuser can change a user's role."
            )
        self.fields["role"].choices = role_choices

    def clean_role(self):
        role = self.cleaned_data.get("role")
        if role == Role.ADMIN and not getattr(self.acting_user, "is_superuser", False):
            raise forms.ValidationError(_("Only the platform superuser can nominate an admin."))
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
