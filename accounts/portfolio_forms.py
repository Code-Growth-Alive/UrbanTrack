"""
Portfolio self-service: experts fill contextual (non-certifying) profile
data: headline, bio, skills, trainings: and pick their preferred CV skin.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import (
    ExpertProfile,
    Mandate,
    MediaAppearance,
    Position,
    Publication,
    Skill,
    TeachingEntry,
    Training,
)

INPUT_CLASS = (
    "mt-1 block w-full rounded-md border border-charcoal-900/25 bg-white px-3 "
    "py-2 text-sm font-normal text-charcoal-900 shadow-none "
    "placeholder:font-normal placeholder:text-charcoal-300 "
    "focus:border-military-500 focus:outline-none focus:ring-2 "
    "focus:ring-military-300"
)


class ProfileForm(forms.ModelForm):
    """Headline / bio / location / civil-status / CV blocks / template."""

    strengths = forms.CharField(
        label=_("Points forts"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": INPUT_CLASS,
                "placeholder": _("Solide relation bailleurs, analyse SIG, …"),
            }
        ),
        help_text=_("Séparez par des virgules — 3 à 5 éléments courts."),
    )
    countries_of_intervention = forms.CharField(
        label=_("Pays d'intervention"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": INPUT_CLASS,
                "placeholder": _("Bénin, Sénégal, Niger"),
            }
        ),
        help_text=_("Séparez par des virgules."),
    )
    languages = forms.CharField(
        label=_("Langues"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": INPUT_CLASS + " font-mono !text-xs",
                "placeholder": _(
                    "French, fluent, fluent, native\n"
                    "English, fluent, fluent, fluent\n"
                    "Arabic, basic, basic, basic"
                ),
            }
        ),
        help_text=_(
            "One language per line: name, level read, level spoken, level written "
            "(e.g. “French, fluent, fluent, native”)."
        ),
    )

    class Meta:
        model = ExpertProfile
        fields = (
            "headline",
            "bio",
            "nationality",
            "phone",
            "birth_date",
            "city",
            "country",
            "cv_template",
            "misc",
            "strengths",
            "countries_of_intervention",
            "languages",
        )
        widgets = {
            "headline": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": _("ex. Urbaniste : villes secondaires résilientes"),
                }
            ),
            "bio": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": INPUT_CLASS,
                    "placeholder": _(
                        "Two or three sentences. Certified projects are shown "
                        "separately below your profile."
                    ),
                }
            ),
            "nationality": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "phone": forms.TextInput(attrs={"class": INPUT_CLASS, "autocomplete": "tel"}),
            "birth_date": forms.DateInput(
                attrs={"class": INPUT_CLASS, "type": "date"},
                format="%Y-%m-%d",
            ),
            "city": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "country": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "cv_template": forms.Select(attrs={"class": INPUT_CLASS + " appearance-none pr-9"}),
            "misc": forms.Textarea(attrs={"rows": 3, "class": INPUT_CLASS}),
        }
        labels = {"cv_template": _("Modèle de CV préféré")}
        help_texts = {
            "cv_template": _(
                "Default skin used for CV exports and by recruiters opening your profile."
            ),
            "birth_date": _("Facultatif, resté confidentiel — jamais affiché sur le site public."),
        }

    def clean_strengths(self):
        return _comma_list(self.cleaned_data["strengths"])

    def clean_countries_of_intervention(self):
        return _comma_list(self.cleaned_data["countries_of_intervention"])

    def clean_languages(self):
        raw = self.cleaned_data["languages"]
        entries = []
        seen = set()
        for line in raw.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0]:
                continue
            name = parts[0]
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            read, spoken, written = (parts[1:4] + ["", "", ""])[:3]
            entries.append(
                {
                    "name": name,
                    "read": read,
                    "spoken": spoken,
                    "written": written,
                }
            )
        return entries


def _comma_list(raw):
    names = []
    for chunk in raw.split(","):
        name = chunk.strip()
        if name and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    return names


class SkillsForm(forms.Form):
    """Comma-separated skill tags, normalised into Skill rows."""

    skills = forms.CharField(
        label=_("Domaines d'expertise"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": INPUT_CLASS,
                "placeholder": _("Urbanisme, analyse SIG, reporting bailleurs"),
            }
        ),
        help_text=_("Séparez les compétences par des virgules."),
    )

    def clean_skills(self):
        raw = self.cleaned_data["skills"]
        names = []
        for chunk in raw.split(","):
            name = chunk.strip()
            if name and name.lower() not in {n.lower() for n in names}:
                names.append(name)
        return names

    def save(self, profile):
        names = self.cleaned_data["skills"]
        skill_objs = []
        for name in names:
            skill, _ = Skill.objects.get_or_create(name=name)
            skill_objs.append(skill)
        profile.skills.set(skill_objs)


class TrainingForm(forms.ModelForm):
    class Meta:
        model = Training
        fields = ("title", "institution", "year")
        widgets = {
            "title": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": _("Master Urbanisme")}
            ),
            "institution": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": _("Institution, ville")}
            ),
            "year": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1950, "max": 2100}),
        }


TrainingFormSet = forms.inlineformset_factory(
    ExpertProfile,
    Training,
    form=TrainingForm,
    extra=0,
    can_delete=True,
)


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ("employer", "function", "date_start", "date_end", "description")
        widgets = {
            "employer": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "function": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": _("ex. Directeur des études")}
            ),
            "date_start": forms.DateInput(
                attrs={"class": INPUT_CLASS, "type": "date"}, format="%Y-%m-%d"
            ),
            "date_end": forms.DateInput(
                attrs={
                    "class": INPUT_CLASS,
                    "type": "date",
                    "placeholder": _("vide = poste actuel"),
                },
                format="%Y-%m-%d",
            ),
            "description": forms.Textarea(attrs={"rows": 2, "class": INPUT_CLASS}),
        }
        help_texts = {
            "date_start": _(
                "Date de début du poste. Le CV les classe de la plus récente à la plus ancienne."
            ),
            "date_end": _("Laissez vide si vous occupez toujours ce poste."),
        }


PositionFormSet = forms.inlineformset_factory(
    ExpertProfile,
    Position,
    form=PositionForm,
    extra=0,
    can_delete=True,
)


class MandateForm(forms.ModelForm):
    class Meta:
        model = Mandate
        fields = ("name", "role", "year_start", "year_end")
        widgets = {
            "name": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": _("e.g. Ordre des architectes")}
            ),
            "role": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "year_start": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1950, "max": 2100}),
            "year_end": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1950, "max": 2100}),
        }


MandateFormSet = forms.inlineformset_factory(
    ExpertProfile,
    Mandate,
    form=MandateForm,
    extra=0,
    can_delete=True,
)


class PublicationForm(forms.ModelForm):
    class Meta:
        model = Publication
        fields = ("title", "venue", "year")
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "venue": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": _("Journal, report, conference…")}
            ),
            "year": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1950, "max": 2100}),
        }


PublicationFormSet = forms.inlineformset_factory(
    ExpertProfile,
    Publication,
    form=PublicationForm,
    extra=0,
    can_delete=True,
)


class TeachingForm(forms.ModelForm):
    class Meta:
        model = TeachingEntry
        fields = ("title", "institution", "year")
        widgets = {
            "title": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": _("e.g. Urban economics (M1)")}
            ),
            "institution": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "year": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1950, "max": 2100}),
        }


TeachingFormSet = forms.inlineformset_factory(
    ExpertProfile,
    TeachingEntry,
    form=TeachingForm,
    extra=0,
    can_delete=True,
)


class MediaForm(forms.ModelForm):
    class Meta:
        model = MediaAppearance
        fields = ("title", "outlet", "year", "url")
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "outlet": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "year": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1950, "max": 2100}),
            "url": forms.URLInput(attrs={"class": INPUT_CLASS}),
        }


MediaFormSet = forms.inlineformset_factory(
    ExpertProfile,
    MediaAppearance,
    form=MediaForm,
    extra=0,
    can_delete=True,
)
