# Generated by Django 2.2 on 2019-09-03 14:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0025_auto_20190903_1654'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='nation',
            field=models.CharField(default='-', max_length=128),
        ),
        migrations.AlterField(
            model_name='skater',
            name='nation',
            field=models.CharField(default='-', max_length=128),
        ),
    ]
