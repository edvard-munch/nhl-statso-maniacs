# Generated by Django 2.2 on 2019-07-02 12:22

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0005_auto_20190702_1515'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='goalie',
            name='draft_number',
        ),
        migrations.RemoveField(
            model_name='goalie',
            name='draft_round',
        ),
        migrations.RemoveField(
            model_name='goalie',
            name='draft_year',
        ),
        migrations.RemoveField(
            model_name='skater',
            name='draft_number',
        ),
        migrations.RemoveField(
            model_name='skater',
            name='draft_round',
        ),
        migrations.RemoveField(
            model_name='skater',
            name='draft_year',
        ),
    ]
