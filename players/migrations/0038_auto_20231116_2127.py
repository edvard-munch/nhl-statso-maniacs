# Generated by Django 2.2.6 on 2023-11-16 18:27

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0037_auto_20231115_1103'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameday',
            name='day',
            field=models.DateField(default=datetime.date(2022, 11, 16), unique=True),
        ),
    ]
