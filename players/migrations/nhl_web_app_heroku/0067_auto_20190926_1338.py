# Generated by Django 2.2 on 2019-09-26 10:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0066_game_date'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='game',
            name='date',
        ),
        migrations.RemoveField(
            model_name='gameday',
            name='games',
        ),
        migrations.AddField(
            model_name='game',
            name='gameday',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='games', to='players.Gameday'),
        ),
    ]
