# Generated by Django 2.2 on 2019-10-04 12:34

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0003_auto_20191004_1524'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='game',
            name='teams',
        ),
    ]