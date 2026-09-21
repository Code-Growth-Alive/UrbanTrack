"""Company-side forms: project publishing and contributor declaration."""

from django import forms
from django.utils.translation import gettext_lazy as _

from certification.models import ConfirmationSource, RoleType

from .models import Client, Country, Funder, Project, ProjectTag

INPUT_CLASS = (
    "mt-1 block w-full rounded-md border border-charcoal-900/25 bg-white px-3 "
    "py-2 text-sm font-normal text-charcoal-900 shadow-none "
    "placeholder:font-normal placeholder:text-charcoal-300 "
    "focus:border-military-500 focus:outline-none focus:ring-2 "
    "focus:ring-military-300"
)
SELECT_CLASS = INPUT_CLASS + " appearance-none bg-white pr-9"


def _find_or_create(model, name_field, raw):
    """Case-insensitive get_or_create on ``name_field``."""
    qs = model._default_manager.filter(**{f"{name_field}__iexact": raw})
    if qs.exists():
        return qs.get()
    return model.objects.create(**{name_field: raw})


class CreatableModelChoiceField(forms.ModelChoiceField):
    """
    T6 structured referential with a free-text UX: typing an existing
    entry reuses it, an unknown name is created. Storage stays structured
    (FK to a normalized table) so filtering and searching keep working.
    """

    def __init__(self, *args, name_field="name", **kwargs):
        self.name_field = name_field
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        value = str(value).strip()
        if not value:
            return None
        try:
            return super().to_python(value)
        except (forms.ValidationError, ValueError, TypeError):
            pass
        return _find_or_create(self.queryset.model, self.name_field, value)


class CreatableModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    """
    T6 comma-separated M2M (thematic keywords): each entered name is reused
    or created, then validated against the referential.
    """

    def __init__(self, *args, name_field="name", **kwargs):
        self.name_field = name_field
        super().__init__(*args, **kwargs)

    def clean(self, value):
        if not value:
            return super().clean([])
        names = [part.strip() for part in value.split(",") if part.strip()]
        saved = [_find_or_create(self.queryset.model, self.name_field, name).pk for name in names]
        return super().clean(saved)


class ProjectForm(forms.ModelForm):
    """Create/edit a draft project (Epic 2 + T6 donor-format enrichment)."""

    country = CreatableModelChoiceField(
        label=_("Pays"),
        queryset=Country.objects.all(),
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": _("ex. Sénégal")}),
    )
    funder = CreatableModelChoiceField(
        label=_("Bailleur"),
        queryset=Funder.objects.all(),
        required=False,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": _("ex. Banque mondiale")}
        ),
    )
    client = CreatableModelChoiceField(
        label=_("Client / maître d'ouvrage"),
        queryset=Client.objects.all(),
        required=False,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": _("ex. Ville de Dakar")}
        ),
    )
    tags = CreatableModelMultipleChoiceField(
        label=_("Mots-clés thématiques"),
        queryset=ProjectTag.objects.all(),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": _("Résilience, assainissement, mobilité"),
            }
        ),
    )

    class Meta:
        model = Project
        fields = (
            "official_name",
            "description",
            "deliverables",
            "duration_start",
            "duration_end",
            "phase",
            "intervention_volume",
            "volume_unit",
            "personal_start",
            "personal_end",
            "budget",
            "client",
            "country",
            "funder",
            "tags",
            "visibility",
        )
        widgets = {
            "official_name": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": _("ex. Réaménagement de la Corniche Ouest de Dakar"),
                }
            ),
            "description": forms.Textarea(attrs={"rows": 5, "class": INPUT_CLASS}),
            "deliverables": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Un livrable par ligne."),
                    "class": INPUT_CLASS,
                }
            ),
            "duration_start": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
            "duration_end": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
            "phase": forms.Select(attrs={"class": SELECT_CLASS}),
            "intervention_volume": forms.NumberInput(
                attrs={"class": INPUT_CLASS, "min": 0, "step": 1}
            ),
            "volume_unit": forms.Select(attrs={"class": SELECT_CLASS}),
            "personal_start": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
            "personal_end": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
            "budget": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": 1}),
            "visibility": forms.Select(attrs={"class": SELECT_CLASS}),
        }
        help_texts = {
            "phase": _("Statut du projet : en cours ou achevé."),
            "personal_start": _(
                "Début de votre participation personnelle (distincte de la durée totale)."
            ),
            "personal_end": _("Laissez vide si votre participation est toujours en cours."),
            "volume_unit": _("jours-personnes ou mois-personnes."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.client_id:
            self.fields["client"].initial = self.instance.client

    def clean(self):
        cleaned = super().clean()
        client = cleaned.get("client")
        legacy_client_name = (self.data.get("client_name") or "").strip()
        if client is None and legacy_client_name:
            client = _find_or_create(Client, "name", legacy_client_name)
            cleaned["client"] = client
        if client is None:
            self.add_error("client", _("Ce champ est obligatoire."))
        return cleaned

    def save(self, commit=True):
        project = super().save(commit=False)
        if project.client:
            project.client_name = project.client.name
        if commit:
            project.save()
            self.save_m2m()
        return project


class ProjectLinkForm(forms.Form):
    """One external reference attached to a published project."""

    label = forms.CharField(label=_("Libellé"), max_length=120)
    url = forms.URLField(label=_("URL"))


class ProjectMediaForm(forms.Form):
    """Attach an image or document to a project (all optional)."""

    KIND_CHOICES = (
        ("image", _("Image")),
        ("document", _("Document")),
    )

    kind = forms.ChoiceField(label=_("Type"), choices=KIND_CHOICES, initial="image")
    caption = forms.CharField(
        label=_("Légende"),
        max_length=200,
        required=False,
        widget=forms.HiddenInput,
    )
    file = forms.FileField(
        label=_("Fichier"),
        required=False,
        help_text=_("Ajoutez un fichier PDF, PNG, JPG ou équivalent."),
    )

    def clean(self):
        cleaned = super().clean()
        file = cleaned.get("file")
        if not file:
            self.add_error("file", _("Veuillez choisir un fichier à importer."))
        return cleaned


class DeclareContributorForm(forms.Form):
    """Declare one expert contributor (existing or by email)."""

    email = forms.EmailField(label=_("Email de l'expert"), max_length=150)
    role_type = forms.ChoiceField(label=_("Rôle"), choices=RoleType.choices)
    confirmation_source = forms.ChoiceField(
        label=_("Qui confirme cette contribution ?"),
        choices=ConfirmationSource.choices,
        initial=ConfirmationSource.EXPERT,
        help_text=_(
            "Expert nommé, client / maître d'ouvrage (consultant individuel), "
            "ou chef de file du groupement (sous-traitance)."
        ),
    )
    contribution_bullets = forms.CharField(
        label=_("Réalisations de l'expert"),
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Une ligne par réalisation concrète de l'expert."),
    )


class RequestClientConfirmationForm(forms.Form):
    """Ask the client / maître d'ouvrage to counter-sign a contribution."""

    contribution_pk = forms.IntegerField(widget=forms.HiddenInput)
    client_email = forms.EmailField(label=_("Email du client"), max_length=150)
