# Generated by Django 2.2 on 2019-09-16 16:52

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0041_auto_20190913_1803'),
    ]

    operations = [
        migrations.AddField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date.today, verbose_name='Date'),
        ),
        migrations.AddField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date.today, verbose_name='Date'),
        ),
    ]
