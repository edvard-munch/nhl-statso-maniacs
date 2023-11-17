# Generated by Django 2.2.6 on 2023-11-10 09:54

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0031_auto_20231110_1244'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameday',
            name='day',
            field=models.DateField(default=datetime.date(2023, 11, 10), unique=True),
        ),
        migrations.AlterField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2023, 11, 10)),
        ),
        migrations.AlterField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2023, 11, 10)),
        ),
    ]
