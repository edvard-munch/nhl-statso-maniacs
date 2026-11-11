"""Atomic account edits shared by JSON settings and the legacy profile editor."""

from contextlib import contextmanager
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction

from .forms import UserUpdateForm, ProfileUpdateForm, MeasurementsFormatEdit
from .models import Profile
from .profile_images import image_changes
from .registration import lock_username, username_constraint_violation

PROFILE_UNAVAILABLE_MESSAGE = "Account profile is missing and requires review."
USER_EDIT_FIELDS = UserUpdateForm.Meta.fields


@dataclass
class AccountEdit:
    user: object
    profile: object
    user_form: object
    image_form: object
    measurements_form: object
    valid: bool


def profile_for(user, *, lock=False):
    profiles = Profile.objects.select_for_update() if lock else Profile.objects
    return profiles.filter(user_id=user.pk).first()


@contextmanager
def edit_account(user, data, *, files=None, full_profile=False):
    """Cooperating web writers lock normalized target name, user, then profile.

    The caller serializes its successful response inside this context so response
    failures roll back database changes. JSON never passes image files here.
    """
    model = get_user_model()
    username = None
    if "username" in data:
        try:
            username = UserUpdateForm().fields["username"].clean(data["username"])
        except ValidationError:
            pass  # The bound form below supplies the original validation errors.
    with image_changes() as images, transaction.atomic():
        if username is not None:
            lock_username(username)
        owner = model.objects.select_for_update().get(pk=user.pk)
        profile = profile_for(owner, lock=True)
        # Bind the fresh profile for any model/signal paths used during editing.
        if profile is not None:
            owner.profile = profile
        uf = (
            UserUpdateForm(data, instance=owner)
            if full_profile or any(field in data for field in USER_EDIT_FIELDS)
            else None
        )
        if uf is not None and not full_profile:
            for field in list(uf.fields):
                if field not in data:
                    uf.fields.pop(field)
        form_profile = profile if profile is not None else Profile(user=owner)
        pf = ProfileUpdateForm(data, files, instance=form_profile) if full_profile else None
        mf = (
            MeasurementsFormatEdit(data, instance=form_profile)
            if full_profile or "measurements_format" in data
            else None
        )
        forms = [form for form in (uf, pf, mf) if form is not None]
        validation = [form.is_valid() for form in forms]
        if profile is None:
            if mf is None:
                mf = MeasurementsFormatEdit({}, instance=form_profile)
                mf.is_valid()
            mf.add_error(None, PROFILE_UNAVAILABLE_MESSAGE)
        valid = profile is not None and all(validation)
        if valid:
            try:
                with transaction.atomic():
                    upload = pf.cleaned_data.get("image") if pf is not None else None
                    if isinstance(upload, UploadedFile):
                        # Form validation placed an uncommitted upload on the
                        # shared instance; restore its stored name before staging.
                        old_name = Profile.objects.only("image").get(pk=profile.pk).image.name
                        profile.image = old_name
                        images.stage(profile, upload)
                    if uf is not None:
                        uf.save()
                    if pf is not None:
                        pf.save()
                    if mf is not None:
                        mf.save()
            except IntegrityError as error:
                if (
                    uf is not None
                    and username is not None
                    and username_constraint_violation(error, model)
                    and model.objects.filter(username__iexact=username)
                    .exclude(pk=owner.pk)
                    .exists()
                ):
                    uf.add_error("username", owner.unique_error_message(model, ["username"]))
                    valid = False
                else:
                    raise
        if valid:
            # Model.clean() may normalize omitted fields in memory; expose only
            # the persisted values after a PATCH, not those transient changes.
            owner.refresh_from_db()
        if profile is not None:
            profile.refresh_from_db()
        yield AccountEdit(owner, profile, uf, pf, mf, valid)
