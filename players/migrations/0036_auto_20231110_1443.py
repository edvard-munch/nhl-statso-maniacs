# Generated by Django 2.2.6 on 2023-11-10 11:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0035_auto_20231110_1318'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='game',
            name='away_skaters',
        ),
        migrations.RemoveField(
            model_name='game',
            name='home_skaters',
        ),
        migrations.AddField(
            model_name='game',
            name='away_defencemen',
            field=models.ManyToManyField(blank=True, related_name='defencemen_away_games', to='players.Skater'),
        ),
        migrations.AddField(
            model_name='game',
            name='away_forwards',
            field=models.ManyToManyField(blank=True, related_name='forwards_away_games', to='players.Skater'),
        ),
        migrations.AddField(
            model_name='game',
            name='home_defencemen',
            field=models.ManyToManyField(blank=True, related_name='defencemen_home_games', to='players.Skater'),
        ),
        migrations.AddField(
            model_name='game',
            name='home_forwards',
            field=models.ManyToManyField(blank=True, related_name='forwards_home_games', to='players.Skater'),
        ),
    ]
