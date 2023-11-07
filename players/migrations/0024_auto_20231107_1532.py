# Generated by Django 2.2.6 on 2023-11-07 12:32

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0023_auto_20230207_1739'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameday',
            name='day',
            field=models.DateField(default=datetime.date(2022, 11, 7), unique=True),
        ),
        migrations.AlterField(
            model_name='goalie',
            name='birth_city',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2022, 11, 7)),
        ),
        migrations.AlterField(
            model_name='skater',
            name='birth_city',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2022, 11, 7)),
        ),
    ]
