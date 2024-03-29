# Generated by Django 2.2.6 on 2019-10-14 10:19

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0008_auto_20191010_1746'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='goalie',
            name='new_gamelog_stats',
        ),
        migrations.RemoveField(
            model_name='skater',
            name='new_gamelog_stats',
        ),
        migrations.AlterField(
            model_name='gameday',
            name='day',
            field=models.DateField(default=datetime.date(2018, 10, 14), unique=True),
        ),
        migrations.AlterField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2018, 10, 14)),
        ),
        migrations.AlterField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2018, 10, 14)),
        ),
    ]
