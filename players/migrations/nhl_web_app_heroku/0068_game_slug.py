# Generated by Django 2.2 on 2019-09-26 11:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0067_auto_20190926_1338'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='slug',
            field=models.SlugField(default='slg'),
            preserve_default=False,
        ),
    ]
