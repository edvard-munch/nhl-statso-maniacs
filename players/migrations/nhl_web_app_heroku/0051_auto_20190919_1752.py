# Generated by Django 2.2 on 2019-09-19 14:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0050_auto_20190919_1752'),
    ]

    operations = [
        migrations.AddField(
            model_name='goalie',
            name='relevant_video',
            field=models.URLField(default='', max_length=128),
        ),
        migrations.AddField(
            model_name='skater',
            name='relevant_video',
            field=models.URLField(default='', max_length=128),
        ),
    ]