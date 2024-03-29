# Generated by Django 2.2 on 2019-09-26 10:11

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0064_auto_20190925_1610'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='game',
            name='date',
        ),
        migrations.AlterField(
            model_name='gameday',
            name='day',
            field=models.DateField(default=datetime.date(2018, 9, 26), unique=True),
        ),
        migrations.AlterField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2018, 9, 26)),
        ),
        migrations.AlterField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2018, 9, 26)),
        ),
    ]
