# Generated by Django 2.2 on 2019-09-27 10:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0080_auto_20190927_1156'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='result',
            field=models.CharField(default='', max_length=20),
        ),
    ]
