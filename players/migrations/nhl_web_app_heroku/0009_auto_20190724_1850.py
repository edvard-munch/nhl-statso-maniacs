# Generated by Django 2.2 on 2019-07-24 15:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0008_auto_20190719_1530'),
    ]

    operations = [
        migrations.RenameField(
            model_name='goalie',
            old_name='compare',
            new_name='comparing',
        ),
        migrations.RenameField(
            model_name='goalie',
            old_name='favorite',
            new_name='favoriting',
        ),
        migrations.RenameField(
            model_name='skater',
            old_name='compare',
            new_name='comparing',
        ),
        migrations.RenameField(
            model_name='skater',
            old_name='favorite',
            new_name='favoriting',
        ),
    ]
