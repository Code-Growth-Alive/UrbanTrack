"""
Public project views.

Only ``published`` + ``public`` projects are served here; this page is the
traceability target of every certified contribution badge on expert
profiles (the "clickable link back to the documented source").
"""

from django.views.generic import DetailView

from .models import Project, ProjectStatus, ProjectVisibility


class ProjectPublicDetailView(DetailView):
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return Project.objects.filter(
            status=ProjectStatus.PUBLISHED,
            visibility=ProjectVisibility.PUBLIC,
        ).select_related("published_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["confirmed_contributions"] = self.object.confirmed_contributions().select_related(
            "expert", "project"
        )
        return context
