"""
Create a rich demo expert so the CV examples and directory have content:
`python manage.py seed_demo_expert` (idempotent).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Company, Skill, User
from certification.services import confirm_as_is, declare_contributor
from projects.models import Project
from projects.services import publish_project

DEMO_PROFILE = {
    "username": "aminata.demo",
    "email": "aminata.sow@demo.urbantrack",
    "password": "Demo!Expert2025",
    "first_name": "Aminata",
    "last_name": "Sow",
    "email_confirmed": True,
}

SKILLS = [
    "Urban planning",
    "Sanitation engineering",
    "Resilience strategy",
    "Feasibility studies",
    "Donor reporting",
    "GIS analysis",
]

TRAININGS = [
    ("MSc Urban Engineering", "Ecole Polytechnique Fédérale de Lausanne", 2012),
    ("BSc Civil Engineering", "Université Cheikh Anta Diop, Dakar", 2009),
]

PROJECTS = [
    {
        "official_name": "Dakar Corniche Ouest redevelopment",
        "description": (
            "Redevelopment of 12 km of coastal public space: promenades, "
            "storm-water management, public lighting and mobility hubs."
        ),
        "deliverables": "Master plan\nDetailed engineering designs\nPublic consultation report",
        "client_name": "City of Dakar",
        "budget": 8500000,
        "role": "manager",
        "bullets": (
            "Led the 12 km coastal redevelopment master plan.\n"
            "Coordinated 4 engineering firms and public consultations."
        ),
    },
    {
        "official_name": "Regional sanitation programme: Petite Côte",
        "description": (
            "Sanitation solutions for 14 coastal towns: sewer networks, "
            "treatment stations, community hygiene programme."
        ),
        "deliverables": "Technical studies\nDonor appraisal dossier\nSupervision reports",
        "client_name": "Ministry of Hydraulics",
        "budget": 12000000,
        "role": "specialist",
        "bullets": (
            "Designed sanitation solutions for 14 coastal towns.\n"
            "Prepared donor appraisal documentation (AFD format)."
        ),
    },
]


class Command(BaseCommand):
    help = "Seed a demo expert with certified projects, skills and trainings."

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=DEMO_PROFILE["username"],
            defaults=DEMO_PROFILE,
        )
        if not created:
            self.stdout.write("demo expert already exists: nothing to do")
            return
        user.set_password(DEMO_PROFILE["password"])
        user.save()

        profile = user.expert_profile
        profile.headline = "Urban planner: resilient secondary cities"
        profile.bio = (
            "Urban planner with twelve years of experience in urban renewal, "
            "sanitation and mobility across West Africa. Certified lead on "
            "donor-financed programmes."
        )
        profile.city = "Dakar"
        profile.country = "Senegal"
        profile.save()
        for name in SKILLS:
            skill, _ = Skill.objects.get_or_create(name=name)
            profile.skills.add(skill)
        from accounts.models import Training

        for title, institution, year in TRAININGS:
            Training.objects.create(
                profile=profile, title=title, institution=institution, year=year
            )

        company_user, _ = User.objects.get_or_create(
            username="demo.corp",
            defaults={
                "username": "demo.corp",
                "email": "corp@demo.urbantrack",
                "password": "Demo!Company2025",
                "first_name": "Fatou",
                "last_name": "Ndiaye",
                "email_confirmed": True,
            },
        )
        company_user.set_password("Demo!Company2025")
        company_user.save()
        company, _ = Company.objects.get_or_create(name="Demo Urban Corp")
        company_user.company = company
        company_user.save(update_fields=["company"])
        for spec in PROJECTS:
            is_corniche = "Corniche" in spec["official_name"]
            project = Project(
                official_name=spec["official_name"],
                description=spec["description"],
                deliverables=spec["deliverables"],
                duration_start="2023-03-01" if is_corniche else "2020-01-01",
                duration_end=None if is_corniche else "2022-12-31",
                budget=spec["budget"],
                client_name=spec["client_name"],
                visibility="public",
                published_by=company_user,
            )
            project.full_clean(exclude=["published_by"])
            project.save()
            publish_project(project)
            contribution = declare_contributor(
                project,
                email=user.email,
                role_type=spec["role"],
                contribution_bullets=spec["bullets"],
                added_by=company_user,
            )
            confirm_as_is(contribution, user)

        self.stdout.write(
            self.style.SUCCESS(
                f"seeded demo expert {user.professional_id} "
                f"({user.email} / {DEMO_PROFILE['password']})"
            )
        )
