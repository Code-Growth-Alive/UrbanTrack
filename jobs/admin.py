from django.contrib import admin

from .models import Job, JobApplication


class JobApplicationInline(admin.TabularInline):
    model = JobApplication
    extra = 0
    fields = ("applicant", "status", "applied_at", "decided_at")
    readonly_fields = ("applied_at", "decided_at")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "published_by", "city", "country", "contract_type",
                    "deadline", "status")
    list_filter = ("status", "contract_type")
    search_fields = ("title", "published_by__email", "city", "country")
    inlines = [JobApplicationInline]


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "applicant", "status", "applied_at", "decided_at")
    list_filter = ("status",)
    search_fields = ("job__title", "applicant__email")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("job", "applicant")
