# Generated by Django 2.2 on 2019-09-17 15:13

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0046_auto_20190917_1813'),
    ]

    operations = [
        migrations.AddField(
            model_name='goalie',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2018, 9, 17)),
        ),
        migrations.AddField(
            model_name='skater',
            name='video_link_updated_at',
            field=models.DateField(default=datetime.date(2018, 9, 17)),
        ),
    ]
