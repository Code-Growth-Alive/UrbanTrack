"""Forms for account creation (role-aware signup) and login."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from .models import Role, User

INPUT_CLASS = (
    "mt-1 block w-full rounded-md border border-charcoal-900/25 bg-white px-3 "
    "py-2 text-sm font-normal text-charcoal-900 shadow-none "
    "placeholder:font-normal placeholder:text-charcoal-300 "
    "focus:border-military-500 focus:outline-none focus:ring-2 "
    "focus:ring-military-300"
)


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    """
    Log in with either the email address or the username.

    Signups use the email as username, but seeded/legacy accounts may have a
    distinct username: both must work everywhere.
    """

    def clean(self):
        identity = self.cleaned_data.get("username")
        if identity and "@" in identity:
            matches = get_user_model().objects.filter(email__iexact=identity)
            if matches.exists():
                self.cleaned_data["username"] = matches.first().username
        return super().clean()


class SignUpForm(forms.Form):
    """Unified signup for the three Urban Track roles.

    Companies and donor agencies must provide an organisation name; experts
    get a portfolio auto-created by the post_save signal.
    """

    ROLE_CHOICES = (
        (Role.EXPERT, Role.EXPERT.label),
        (Role.COMPANY, Role.COMPANY.label),
        (Role.DONOR, Role.DONOR.label),
    )

    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    email = forms.EmailField(label=_("Email address"), max_length=150)
    role = forms.ChoiceField(
        label=_("I am"),
        choices=ROLE_CHOICES,
        initial=Role.EXPERT,
        widget=forms.RadioSelect,
    )
    organisation_name = forms.CharField(
        label=_("Organisation name"),
        max_length=255,
        required=False,
        help_text=_("Required for companies and donor agencies."),
    )
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Confirm password"), widget=forms.PasswordInput)

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account already exists with this email address."))
        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        if role and role != Role.EXPERT and not cleaned.get("organisation_name"):
            self.add_error(
                "organisation_name",
                _("An organisation name is required for this account type."),
            )
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("The two passwords do not match."))
        if password1:
            validate_password(password1)
        return cleaned

    def create_user(self):
        """Persist the account; username mirrors the unique email."""
        data = self.cleaned_data
        user = User(
            username=data["email"],
            email=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=data["role"],
            organisation_name=data.get("organisation_name", ""),
        )
        user.set_password(data["password1"])
        user.save()
        return user


class AccountSettingsForm(forms.ModelForm):
    """
    Shared account settings: personal details, organisation name and the
    profile picture (avatar). Email and username stay immutable once set;
    password changes go through ``PasswordChangeView``.
    """

    class Meta:
        model = User
        fields = ("first_name", "last_name", "organisation_name", "avatar")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "organisation_name": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": _("Only used for company and donor accounts."),
                }
            ),
            "avatar": forms.ClearableFileInput(
                attrs={
                    "class": (
                        INPUT_CLASS
                        + " !p-1.5 file:mr-3 file:rounded file:border-0 file:bg-military-100 "
                        "file:px-3 file:py-1 file:text-xs file:font-semibold file:text-military-700"
                    )
                }
            ),
        }
        help_texts = {
            "avatar": _("JPG or PNG portrait. Leave empty to keep your current picture."),
        }
