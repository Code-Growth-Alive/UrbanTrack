"""Accounts app utilities: professional ID generation (spec OF-02)."""

import secrets

from django.conf import settings

# Retry budget when racing against the unique constraint on professional_id.
MAX_ID_GENERATION_ATTEMPTS = 10


def generate_professional_id():
    """
    Return a new candidate professional ID in the ``OX-XXXXXX`` format.

    Uses a cryptographically secure generator and an alphabet stripped of
    visually ambiguous characters (I, O, 0, 1) so IDs stay readable on CVs,
    badges and over the phone. Uniqueness is guaranteed by the caller
    (``User.save``) via a pre-save check plus the database unique constraint.
    """
    alphabet = settings.PROFESSIONAL_ID_ALPHABET
    length = settings.PROFESSIONAL_ID_LENGTH
    code = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{settings.PROFESSIONAL_ID_PREFIX}-{code}"
