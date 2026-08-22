"""
Public expert profile (ResearchGate-style page).

The profile lists ONLY cross-confirmed experiences: company declared,
expert personally validated. Each entry carries the certification badge and
a clickable, traceable link back to the public project page.
"""

from django.views.generic import DetailView

from .models import Role, User


class PublicExpertProfileView(DetailView):
    model = User
    slug_field = "professional_id"
    slug_url_kwarg = "professional_id"
    queryset = User.objects.filter(role=Role.EXPERT)
    template_name = "experts/profile.html"
    context_object_name = "expert"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = getattr(self.object, "expert_profile", None)
        contributions = list(profile.confirmed_contributions()) if profile else []
        by_role = {}
        for contribution in contributions:
            by_role[contribution.role_type] = by_role.get(contribution.role_type, 0) + 1
        context.update(
            profile=profile,
            confirmed_contributions=contributions,
            stats={
                "total": len(contributions),
                "director": by_role.get("director", 0),
                "manager": by_role.get("manager", 0),
                "specialist": by_role.get("specialist", 0),
                "assistant": by_role.get("assistant", 0),
            },
            trust_score=profile.trust_score() if profile else 0,
        )
        return context
