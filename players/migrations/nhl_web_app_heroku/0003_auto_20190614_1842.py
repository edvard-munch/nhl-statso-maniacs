# Generated by Django 2.2 on 2019-06-14 15:42

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0002_auto_20190614_1832'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='goalie',
            name='test',
        ),
        migrations.RemoveField(
            model_name='skater',
            name='test',
        ),
        migrations.AlterField(
            model_name='goalie',
            name='team',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='gls', to='players.Team'),
        ),
        migrations.AlterField(
            model_name='skater',
            name='team',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sks', to='players.Team'),
        ),
    ]