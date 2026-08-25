"""
Portfolio self-service: experts fill contextual (non-certifying) profile
data: headline, bio, skills, trainings: and pick their preferred CV skin.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ExpertProfile, Skill, Training

INPUT_CLASS = (
    "mt-1 block w-full rounded-md border border-charcoal-900/25 bg-white px-3 "
    "py-2 text-sm font-normal text-charcoal-900 shadow-none "
    "placeholder:font-normal placeholder:text-charcoal-300 "
    "focus:border-military-500 focus:outline-none focus:ring-2 "
    "focus:ring-military-300"
)


class ProfileForm(forms.ModelForm):
    """Headline / bio / location / preferred CV template."""

    class Meta:
        model = ExpertProfile
        fields = ("headline", "bio", "city", "country", "cv_template")
        widgets = {
            "headline": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": _("e.g. Urban planner: resilient secondary cities"),
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
            "city": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "country": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "cv_template": forms.Select(
                attrs={"class": INPUT_CLASS + " appearance-none pr-9"}
            ),
        }
        labels = {"cv_template": _("Preferred CV template")}
        help_texts = {
            "cv_template": _(
                "Default skin used for CV exports and by recruiters opening "
                "your profile."
            ),
        }


class SkillsForm(forms.Form):
    """Comma-separated skill tags, normalised into Skill rows."""

    skills = forms.CharField(
        label=_("Areas of expertise"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": INPUT_CLASS,
                "placeholder": _("Urban planning, GIS analysis, donor reporting"),
            }
        ),
        help_text=_("Separate skills with commas."),
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
                attrs={"class": INPUT_CLASS,
                       "placeholder": _("MSc Urban Engineering")}
            ),
            "institution": forms.TextInput(
                attrs={"class": INPUT_CLASS,
                       "placeholder": _("Institution, city")}
            ),
            "year": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "min": 1950, "max": 2100}
            ),
        }


TrainingFormSet = forms.inlineformset_factory(
    ExpertProfile,
    Training,
    form=TrainingForm,
    extra=2,
    can_delete=True,
)
