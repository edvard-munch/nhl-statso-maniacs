# Generated by Django 2.2.6 on 2020-01-09 15:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0018_auto_20200109_1814'),
    ]

    operations = [
        migrations.AlterField(
            model_name='skater',
            name='assists',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='assists_avg',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='goals',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='goals_avg',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='penalty_min',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='penalty_min_avg',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='plus_minus',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='plus_minus_avg',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='points',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='points_avg',
            field=models.FloatField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='shots',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='skater',
            name='shots_avg',
            field=models.FloatField(null=True),
        ),
    ]
