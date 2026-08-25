"""
Expert-facing surfaces of the certification flow (Epic 3):

* the magic-link landing for invited (unregistered) experts;
* a per-contribution review page for registered experts, reachable from
  their dashboard: registered experts never receive a token.

Both surfaces share one action handler so the state machine is driven from
exactly one place.
"""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from .models import ContributionStatus, ProjectContribution, RoleType
from .services import (
    CertificationError,
    adjust_contribution,
    confirm_as_is,
    dispute_contribution,
    get_by_token,
    mark_invitation_opened,
    reject_contribution,
)


class InvalidActionError(CertificationError):
    """Unknown action posted to a review surface."""


def _actor_matches(contribution, user):
    """True when ``user`` is the named expert (linked or by email match)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if contribution.expert_id:
        return contribution.expert_id == user.pk
    return user.email.lower() == contribution.invited_email.lower()


def _review_context(contribution, invitation=None, extra=None):
    context = {
        "invitation": invitation,
        "contribution": contribution,
        "project": contribution.project,
        "company_name": (
            contribution.added_by.organisation_name
            or contribution.added_by.get_full_name()
            or contribution.added_by.email
        ),
        "is_actionable": contribution.status in ContributionStatus.actionable()
        and not contribution.pending_company_validation,
        "role_options": RoleType.choices,
    }
    if extra:
        context.update(extra)
    return context


def _handle_action(request, contribution, invitation):
    """
    Apply one expert action and answer with a redirect back to the surface
    that posted it. Raises PermissionDeniedError for mismatched actors.
    """
    named_actor = _actor_matches(contribution, request.user)
    back = request.path

    if request.user.is_authenticated and not named_actor:
        raise PermissionDenied(_("Only the named expert can act on this contribution."))

    action = request.POST.get("action")
    try:
        if action == "confirm":
            confirm_as_is(contribution, request.user)
            messages.success(
                request,
                _("Your contribution is now certified via cross-confirmation."),
            )
        elif action == "adjust":
            bullets = (request.POST.get("contribution_bullets") or "").strip()
            role = request.POST.get("role_type") or None
            if not bullets:
                raise ValidationError(_("Please describe your actual contribution."))
            adjust_contribution(
                contribution,
                request.user,
                contribution_bullets=bullets,
                role_type=role,
            )
            messages.success(
                request,
                _("Adjusted wording saved: it now awaits validation by %(company)s.")
                % {"company": contribution.added_by.organisation_name or _("the company")},
            )
        elif action == "reject":
            reject_contribution(contribution, request.user, reason=request.POST.get("reason", ""))
            messages.success(request, _("The contribution was rejected."))
        elif action == "dispute":
            dispute_contribution(contribution, request.user, reason=request.POST.get("reason", ""))
            messages.success(
                request,
                _("The contribution is now disputed and an administrator will arbitrate."),
            )
        else:
            raise InvalidActionError()
    except (CertificationError, ValidationError) as error:
        message_dict = getattr(error, "message_dict", None)
        flat = (
            "; ".join(msgs for msgs in message_dict.values() for msgs in msgs)
            if isinstance(message_dict, dict)
            else str(error)
        )
        messages.error(request, flat)
    return redirect(back)


@require_http_methods(["GET", "POST"])
def invitation_landing(request, token):
    """Pre-filled landing page reached through the magic link."""
    invitation = get_by_token(token)
    if invitation is None:
        return render(
            request,
            "certification/invitation_invalid.html",
            status=404,
        )

    contribution = invitation.contribution

    if request.method == "POST":
        if request.POST.get("action") == "signup":
            if request.user.is_authenticated:
                return redirect(request.path)
            return _handle_signup(request, invitation, contribution)
        if not request.user.is_authenticated:
            messages.error(request, _("Please log in to act on this contribution."))
            return redirect(f"{request.path}?next={request.path}")
        try:
            return _handle_action(request, contribution, invitation)
        except PermissionDenied:
            messages.error(
                request,
                _("Only the named expert can act on this contribution."),
            )
            return redirect(request.path)

    # GET: opening the link marks the invitation opened (Epic 6 tracking hook).
    mark_invitation_opened(invitation)

    from accounts.forms import SignUpForm

    extra = {"named_actor": _actor_matches(contribution, request.user)}
    if not request.user.is_authenticated and not contribution.expert_id:
        extra["signup_form"] = SignUpForm(initial={"email": contribution.invited_email})
    elif request.user.is_authenticated:
        extra["mismatched_user"] = not extra["named_actor"]
    return render(
        request,
        "certification/invitation_landing.html",
        _review_context(contribution, invitation=invitation, extra=extra),
    )


def _handle_signup(request, invitation, contribution):
    """Create the expert account inline (email locked to the invitation)."""
    from accounts.forms import SignUpForm

    data = request.POST.copy()
    data["email"] = contribution.invited_email
    data["role"] = "expert"
    form = SignUpForm(data)
    if not form.is_valid():
        return render(
            request,
            "certification/invitation_landing.html",
            _review_context(
                contribution,
                invitation=invitation,
                extra={"signup_form": form, "signup_open": True},
            ),
            status=400,
        )
    user = form.create_user()
    login(request, user)
    messages.success(
        request,
        _("Welcome to Urban Track! Your account is ready: review your contribution below."),
    )
    return redirect("certification:invitation_landing", token=invitation.token)


@login_required
@require_http_methods(["GET", "POST"])
def contribution_review(request, pk):
    """
    Review surface for REGISTERED experts (dashboard entry point).

    Same panels and actions as the magic-link landing, but guarded purely by
    account identity: only the linked expert (or an exact invited-email
    match) may view and act: pks are sequential, so access is denied
    outright to anyone else.
    """
    contribution = get_object_or_404(
        ProjectContribution.objects.select_related("project", "added_by", "expert"),
        pk=pk,
    )
    if not _actor_matches(contribution, request.user):
        raise PermissionDenied(_("Only the named expert can act on this contribution."))

    if request.method == "POST":
        _handle_action(request, contribution, invitation=None)
        return redirect("certification:contribution_review", pk=contribution.pk)

    return render(
        request,
        "certification/invitation_landing.html",
        _review_context(contribution, extra={"named_actor": True}),
    )
