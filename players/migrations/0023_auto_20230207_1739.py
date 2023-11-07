# Generated by Django 2.2.6 on 2023-02-07 14:39

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0022_auto_20230201_1648'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameday',
            name='day',
            field=models.DateField(default=datetime.date(2022, 2, 7), unique=True),
        ),
        migrations.AlterField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2022, 2, 7)),
        ),
        migrations.AlterField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2022, 2, 7)),
        ),
    ]