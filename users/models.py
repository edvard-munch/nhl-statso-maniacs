from django.db import models
from django.contrib.auth.models import User
from users.choices import *


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(default='default.jpg', upload_to='profile_pics')
    measurements_format = models.CharField(choices=MEASUREMENTS_FORMAT_CHOICES,
                                            max_length=55, default='USA')

    def __str__(self):
        return f'{self.user.username} Profile'

    # create AWS lambda function for resizing images

    # def save(self, force_insert=False, force_update=False, using=None):
    #     # *args, **kwargs ???
    #     super().save()
    #
    #     img = Image.open(self.image.path)
    #
    #     if img.height > 300 or img.width > 300:
    #         output_size = (300, 300)
    #         img.thumbnail(output_size)
    #         img.save(self.image.path)
