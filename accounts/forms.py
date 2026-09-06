"""Forms for account creation (role-aware signup) and login."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm as DjangoPasswordResetForm
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from .models import Company, Role, User

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


class PasswordResetForm(DjangoPasswordResetForm):
    """
    Let a user reset their password by providing either their email or their
    username. Usernames mirror email addresses for new signups, but seeded /
    legacy accounts may have a distinct username, so both must work.
    """

    email = forms.CharField(
        label=_("Email or username"),
        max_length=254,
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )

    def clean_email(self):
        identifier = self.cleaned_data["email"].strip()
        if "@" in identifier:
            identifier = get_user_model().objects.normalize_email(identifier)
        else:
            matches = get_user_model().objects.filter(username__iexact=identifier)
            if matches.exists():
                identifier = matches.first().email
        self.cleaned_data["email"] = identifier
        return identifier


class SignUpForm(forms.Form):
    """Account creation for every user (the only account type besides admin).

    The user may type a company name: it is looked up case-insensitively and
    reused if it already exists, otherwise a new ``Company`` is created and
    the user joins it.
    """

    first_name = forms.CharField(label=_("First name"), max_length=150)
    last_name = forms.CharField(label=_("Last name"), max_length=150)
    email = forms.EmailField(label=_("Email address"), max_length=150)
    company_name = forms.CharField(
        label=_("Company / organisation (optional)"),
        max_length=255,
        required=False,
        help_text=_(
            "Type your company name. If it already exists you will join it, "
            "otherwise a new company is created for you."
        ),
    )
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Confirm password"), widget=forms.PasswordInput)

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account already exists with this email address."))
        return email

    def clean_company_name(self):
        name = self.cleaned_data.get("company_name", "").strip()
        return name.strip()

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("The two passwords do not match."))
        if password1:
            validate_password(password1)
        return cleaned

    def _resolve_company(self):
        """Create or reuse a Company by name (case-insensitive)."""
        name = self.cleaned_data.get("company_name") or ""
        if not name:
            return None
        company = Company.objects.filter(name__iexact=name).first()
        if company is not None:
            return company
        return Company.objects.create(name=name)

    def create_user(self):
        """Persist the account as role ``user``, linked to its company."""
        data = self.cleaned_data
        user = User(
            username=data["email"],
            email=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=Role.USER,
            company=self._resolve_company(),
        )
        user.set_password(data["password1"])
        user.save()
        return user


class ConfirmEmailForm(forms.Form):
    """Validate the 6-digit confirmation code received by email."""

    code = forms.CharField(
        label=_("Confirmation code"),
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "placeholder": "123456",
            }
        ),
    )


class EmailChangeForm(forms.ModelForm):
    """Change the account email; a fresh confirmation code is then required."""

    class Meta:
        model = User
        fields = ("email",)
        widgets = {
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS, "autocomplete": "email"}),
        }

    def clean_email(self):
        email = get_user_model().objects.normalize_email(self.cleaned_data["email"])
        qs = get_user_model().objects.filter(email__iexact=email)
        if qs.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("An account already uses this email address."))
        return email


class AccountSettingsForm(forms.ModelForm):
    """
    Shared account settings: personal details, profile picture and company.

    Email and username stay immutable once set (changing the email requires
    a fresh confirmation code); password changes go through
    ``PasswordChangeView``.
    """

    class Meta:
        model = User
        fields = ("first_name", "last_name", "company", "avatar")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "company": forms.Select(attrs={"class": INPUT_CLASS}),
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
