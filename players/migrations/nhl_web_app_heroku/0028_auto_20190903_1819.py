# Generated by Django 2.2 on 2019-09-03 15:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0027_auto_20190903_1819'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='birth_state',
            field=models.CharField(default='montana', max_length=128),
        ),
        migrations.AlterField(
            model_name='skater',
            name='birth_state',
            field=models.CharField(default='montana', max_length=128),
        ),
    ]