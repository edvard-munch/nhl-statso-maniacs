# Generated by Django 2.2.6 on 2023-12-18 09:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0042_auto_20231217_2023'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameday',
            name='all_games_scheduled',
            field=models.BooleanField(default=False),
        ),
    ]
