# Generated by Django 2.2 on 2019-09-03 12:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0019_auto_20190903_1518'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='nation_abbr',
            field=models.CharField(default='', max_length=128, null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='nation_abbr',
            field=models.CharField(default='', max_length=128, null=True),
        ),
    ]
