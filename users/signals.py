from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Profile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, created, update_fields=None, **kwargs):
    # Login and field-limited account saves must not persist a stale cached
    # profile. Explicit profile editors save their own freshly locked instance.
    if not created and update_fields is not None:
        return
    instance.profile.save()
