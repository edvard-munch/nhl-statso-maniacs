# Generated by Django 2.2 on 2019-09-20 09:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0052_auto_20190920_1256'),
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