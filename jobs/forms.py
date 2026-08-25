"""Job board forms."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Job

INPUT_CLASS = (
    "mt-1 block w-full rounded-md border border-charcoal-900/25 bg-white px-3 "
    "py-2 text-sm font-normal text-charcoal-900 shadow-none "
    "placeholder:font-normal placeholder:text-charcoal-300 "
    "focus:border-military-500 focus:outline-none focus:ring-2 "
    "focus:ring-military-300"
)


class JobForm(forms.ModelForm):
    """Publish a job offer (Epic 8)."""

    class Meta:
        model = Job
        fields = (
            "title",
            "city",
            "country",
            "contract_type",
            "description",
            "requirements",
            "compensation",
            "deadline",
        )
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": _("e.g. Senior urban planner: secondary cities programme"),
                }
            ),
            "city": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": _("Dakar")}),
            "country": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": _("Senegal")}),
            "contract_type": forms.Select(attrs={"class": INPUT_CLASS + " appearance-none pr-9"}),
            "description": forms.Textarea(attrs={"rows": 6, "class": INPUT_CLASS}),
            "requirements": forms.Textarea(
                attrs={"rows": 4, "class": INPUT_CLASS,
                       "placeholder": _("One requirement per line.")}
            ),
            "compensation": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "deadline": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
        }


class ApplicationForm(forms.Form):
    """Expert application form."""

    cover_letter = forms.CharField(
        label=_("Cover letter"),
        widget=forms.Textarea(
            attrs={"rows": 6, "class": INPUT_CLASS.replace("mt-1 ", "")}
        ),
        help_text=_("Reference your certified projects: recruiters see them first."),
    )
