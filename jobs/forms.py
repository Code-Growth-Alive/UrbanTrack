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
                    "placeholder": _("ex. Urbaniste principal : programme villes secondaires"),
                }
            ),
            "city": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": _("Dakar")}),
            "country": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": _("Sénégal")}),
            "contract_type": forms.Select(attrs={"class": INPUT_CLASS + " appearance-none pr-9"}),
            "description": forms.Textarea(attrs={"rows": 6, "class": INPUT_CLASS}),
            "requirements": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": INPUT_CLASS,
                    "placeholder": _("Un prérequis par ligne."),
                }
            ),
            "compensation": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "deadline": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
        }


class ApplicationForm(forms.Form):
    """Expert application form."""

    cover_letter = forms.CharField(
        label=_("Lettre de motivation"),
        widget=forms.Textarea(attrs={"rows": 6, "class": INPUT_CLASS.replace("mt-1 ", "")}),
        help_text=_("Référencez vos projets certifiés : les recruteurs les voient en premier."),
    )
