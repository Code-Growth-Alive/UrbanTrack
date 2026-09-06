"""Company-side forms: project publishing and contributor declaration."""

from django import forms
from django.utils.translation import gettext_lazy as _

from certification.models import RoleType

from .models import Project

INPUT_CLASS = (
    "mt-1 block w-full rounded-md border border-charcoal-900/25 bg-white px-3 "
    "py-2 text-sm font-normal text-charcoal-900 shadow-none "
    "placeholder:font-normal placeholder:text-charcoal-300 "
    "focus:border-military-500 focus:outline-none focus:ring-2 "
    "focus:ring-military-300"
)
SELECT_CLASS = INPUT_CLASS + " appearance-none bg-white pr-9"


class ProjectForm(forms.ModelForm):
    """Create/edit a draft project (Epic 2 screen)."""

    class Meta:
        model = Project
        fields = (
            "official_name",
            "description",
            "deliverables",
            "duration_start",
            "duration_end",
            "budget",
            "client_name",
            "visibility",
        )
        widgets = {
            "official_name": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": _("e.g. Dakar Corniche Ouest redevelopment"),
                }
            ),
            "description": forms.Textarea(attrs={"rows": 5, "class": INPUT_CLASS}),
            "deliverables": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("One deliverable per line."),
                    "class": INPUT_CLASS,
                }
            ),
            "duration_start": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
            "duration_end": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
            "budget": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": 1}),
            "client_name": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": _("e.g. City of Dakar")}
            ),
            "visibility": forms.Select(attrs={"class": SELECT_CLASS}),
        }


class ProjectLinkForm(forms.Form):
    """One external reference attached to a published project."""

    label = forms.CharField(label=_("Label"), max_length=120)
    url = forms.URLField(label=_("URL"))


class ProjectMediaForm(forms.Form):
    """Attach an image or document to a project (all optional)."""

    KIND_CHOICES = (
        ("image", _("Image")),
        ("document", _("Document")),
    )

    kind = forms.ChoiceField(label=_("Type"), choices=KIND_CHOICES, initial="image")
    caption = forms.CharField(
        label=_("Caption"),
        max_length=200,
        required=False,
        widget=forms.HiddenInput,
    )
    file = forms.FileField(
        label=_("File"),
        required=False,
        help_text=_("Upload a PDF, PNG, JPG or similar file."),
    )

    def clean(self):
        cleaned = super().clean()
        file = cleaned.get("file")
        if not file:
            self.add_error("file", _("Please choose a file to upload."))
        return cleaned


class DeclareContributorForm(forms.Form):
    """Declare one expert contributor (existing or by email)."""

    email = forms.EmailField(label=_("Expert email"), max_length=150)
    role_type = forms.ChoiceField(label=_("Role"), choices=RoleType.choices)
    contribution_bullets = forms.CharField(
        label=_("Contribution bullets"),
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("One bullet per line describing what the expert delivered."),
    )
