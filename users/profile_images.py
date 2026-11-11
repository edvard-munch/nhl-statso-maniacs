"""Validated API avatars and request-lifetime cleanup shared with HTML image writes."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO
import logging
from pathlib import PurePosixPath
import re
from uuid import uuid4
import warnings

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from .forms import ProfileUpdateForm
from .models import Profile

logger = logging.getLogger(__name__)
MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
MAX_AVATAR_DIMENSION = 8192
MAX_AVATAR_FRAMES = 1
MAX_FILENAME_ATTEMPTS = 5
FORMAT_EXTENSIONS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
FORMAT_MIME_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
SAFE_EXTENSION = re.compile(r"[a-z0-9]{1,10}")


def validate_avatar(upload):
    """Bounded still-image decoding; never trust the supplied name or MIME type."""
    try:
        upload.seek(0)
        content = upload.read(MAX_AVATAR_BYTES + 1)
        upload.seek(0)
        if not content or len(content) > MAX_AVATAR_BYTES:
            raise ValidationError("Supply a nonempty image of at most 5 MiB.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                format_ = image.format
                if format_ not in FORMAT_EXTENSIONS:
                    raise ValidationError("Use a PNG, JPEG or WebP image.")
                if (
                    image.width * image.height > MAX_AVATAR_PIXELS
                    or max(image.size) > MAX_AVATAR_DIMENSION
                ):
                    raise ValidationError("Image dimensions exceed the avatar limits.")
                if getattr(image, "n_frames", MAX_AVATAR_FRAMES) > MAX_AVATAR_FRAMES:
                    raise ValidationError("Use a still image, not an animation.")
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
        suffix = FORMAT_EXTENSIONS[format_]
        canonical = SimpleUploadedFile(
            "avatar." + suffix, content, content_type=FORMAT_MIME_TYPES[format_]
        )
        # Preserve the existing form's image validation in addition to API bounds.
        return ProfileUpdateForm().fields["image"].clean(canonical)
    except ValidationError:
        raise
    except (
        OSError,
        SyntaxError,
        EOFError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValidationError("Supply a valid, complete image.") from None


def managed_name(name):
    image_field = Profile._meta.get_field("image")
    if not name or name == image_field.get_default() or not isinstance(name, str):
        return False
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
        and name.startswith(image_field.upload_to.rstrip("/") + "/")
    )


def delete_unreferenced(storage, name):
    if not managed_name(name):
        return
    try:
        if not Profile.objects.filter(image=name).exists():
            storage.delete(name)
    except Exception:
        # A committed update must not become a false failure because old-file
        # cleanup failed. Leave the residual file and log it for investigation.
        logger.exception("Profile image cleanup failed for %s", name)


@dataclass
class ImageChanges:
    created: list = field(default_factory=list)

    def stage(self, profile, upload):
        image_field = Profile._meta.get_field("image")
        storage = image_field.storage
        format_ = getattr(getattr(upload, "image", None), "format", None)
        suffix = FORMAT_EXTENSIONS.get(format_) or PurePosixPath(upload.name).suffix.lower().lstrip(
            "."
        )
        if not SAFE_EXTENSION.fullmatch(suffix):
            raise ValidationError("Invalid image extension.")
        for _ in range(MAX_FILENAME_ATTEMPTS):
            candidate = image_field.generate_filename(profile, uuid4().hex + "." + suffix)
            if not storage.exists(candidate):
                break
        else:
            raise OSError("Cannot allocate a unique profile image name")
        old_name = profile.image.name
        self.created.append((storage, candidate))
        upload.seek(0)
        saved = storage.save(candidate, upload, max_length=image_field.max_length)
        if saved != candidate:
            self.created.append((storage, saved))
        # Assign a committed name so model/signals cannot upload these bytes twice.
        profile.image = saved
        transaction.on_commit(lambda: delete_unreferenced(storage, old_name))

    def reset(self, profile):
        old_name = profile.image.name
        storage = profile.image.storage
        profile.image = Profile._meta.get_field("image").get_default()
        transaction.on_commit(lambda: delete_unreferenced(storage, old_name))


@contextmanager
def image_changes():
    changes = ImageChanges()
    try:
        yield changes
    finally:
        # Runs after the caller's database transaction exits. Referenced files
        # survive; files from failed saves/serialization/savepoints are removed.
        for storage, name in changes.created:
            delete_unreferenced(storage, name)
