# Generated by Django 2.2 on 2019-09-17 15:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0047_auto_20190917_1813'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='goalie',
            name='video_link_updated_at',
        ),
        migrations.RemoveField(
            model_name='skater',
            name='video_link_updated_at',
        ),
    ]
