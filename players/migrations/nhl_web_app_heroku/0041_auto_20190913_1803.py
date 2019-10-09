# Generated by Django 2.2 on 2019-09-13 15:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0040_auto_20190903_1923'),
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
