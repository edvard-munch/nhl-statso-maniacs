# Generated by Django 2.2.6 on 2020-05-15 12:20

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0020_auto_20200109_1821'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameday',
            name='day',
            field=models.DateField(default=datetime.date(2019, 5, 15), unique=True),
        ),
        migrations.AlterField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2019, 5, 15)),
        ),
        migrations.AlterField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2019, 5, 15)),
        ),
    ]