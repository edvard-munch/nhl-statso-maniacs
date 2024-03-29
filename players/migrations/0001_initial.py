# Generated by Django 2.2 on 2019-10-03 15:07

import datetime
from django.conf import settings
import django.contrib.postgres.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import players.storage


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Gameday',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(default=datetime.date(2018, 10, 3), unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('nhl_id', models.IntegerField(unique=True)),
                ('abbr', models.CharField(max_length=128)),
                ('slug', models.SlugField()),
                ('image', models.ImageField(storage=players.storage.OverwriteStorage(), upload_to='teams_logos')),
                ('arena_name', models.CharField(max_length=128)),
                ('arena_location', models.CharField(max_length=128)),
                ('division', models.CharField(max_length=128)),
                ('conference', models.CharField(max_length=128)),
                ('off_site', models.URLField(max_length=128)),
                ('nhl_debut', models.CharField(max_length=128)),
            ],
        ),
        migrations.CreateModel(
            name='Skater',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('first_name', models.CharField(max_length=128)),
                ('last_name', models.CharField(max_length=128)),
                ('nhl_id', models.IntegerField(unique=True)),
                ('slug', models.SlugField()),
                ('image', models.ImageField(default='skater_default.png', storage=players.storage.OverwriteStorage(), upload_to='players_pics')),
                ('relevant_video', models.URLField(default='', max_length=128)),
                ('video_link_updated_at', models.DateField(default=datetime.date(2018, 10, 3))),
                ('position_abbr', models.CharField(max_length=128)),
                ('position_name', models.CharField(max_length=128)),
                ('height', models.CharField(max_length=128)),
                ('height_cm', models.IntegerField(null=True)),
                ('weight', models.IntegerField(null=True)),
                ('weight_kg', models.IntegerField(null=True)),
                ('birth_date', models.DateField()),
                ('birth_city', models.CharField(default='', max_length=128)),
                ('birth_state', models.CharField(default='', max_length=128)),
                ('birth_country', models.CharField(default='', max_length=128)),
                ('birth_country_abbr', models.CharField(default='', max_length=128)),
                ('nation', models.CharField(default='', max_length=128)),
                ('nation_abbr', models.CharField(blank=True, default='', max_length=128)),
                ('nation_flag', models.ImageField(default='flag.png', upload_to='flags')),
                ('draft_year', models.IntegerField(null=True)),
                ('draft_round', models.IntegerField(null=True)),
                ('draft_number', models.IntegerField(null=True)),
                ('pl_number', models.IntegerField(null=True)),
                ('age', models.IntegerField(null=True)),
                ('roster_status', models.CharField(max_length=128)),
                ('nhl_debut', models.CharField(max_length=12)),
                ('rookie', models.BooleanField(default=False)),
                ('captain', models.BooleanField(default=False)),
                ('alt_captain', models.BooleanField(default=False)),
                ('sbs_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('career_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('gamelog_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('games', models.IntegerField()),
                ('multiteams_seasons', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('seasons_count', models.IntegerField(null=True)),
                ('proj_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('new_gamelog_stats', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('goals', models.IntegerField()),
                ('goals_avg', models.FloatField()),
                ('assists', models.IntegerField()),
                ('assists_avg', models.FloatField()),
                ('points', models.IntegerField()),
                ('points_avg', models.FloatField()),
                ('plus_minus', models.IntegerField()),
                ('plus_minus_avg', models.FloatField()),
                ('penalty_min', models.IntegerField()),
                ('penalty_min_avg', models.FloatField()),
                ('shots', models.IntegerField()),
                ('shots_avg', models.FloatField()),
                ('hits', models.IntegerField(null=True)),
                ('hits_avg', models.FloatField(null=True)),
                ('blocks', models.IntegerField(null=True)),
                ('blocks_avg', models.FloatField(null=True)),
                ('faceoff_wins', models.IntegerField(null=True)),
                ('faceoff_wins_avg', models.FloatField(null=True)),
                ('pp_points', models.IntegerField()),
                ('pp_points_avg', models.FloatField()),
                ('sh_points', models.IntegerField()),
                ('sh_points_avg', models.FloatField()),
                ('time_on_ice', models.CharField(max_length=128)),
                ('time_on_ice_pp', models.CharField(max_length=128)),
                ('time_on_ice_sh', models.CharField(max_length=128)),
                ('fw_stats', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('sbs_stats_avg', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('career_stats_avg', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('comparing', models.ManyToManyField(blank=True, related_name='comparable_skaters', to=settings.AUTH_USER_MODEL)),
                ('favoriting', models.ManyToManyField(blank=True, related_name='favorite_skaters', to=settings.AUTH_USER_MODEL)),
                ('team', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='skaters', to='players.Team')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Position',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(blank=True, max_length=5), blank=True, default=list, size=None)),
                ('player_name', models.CharField(max_length=80)),
                ('object_id', models.PositiveIntegerField(null=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('content_type', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
            ],
        ),
        migrations.CreateModel(
            name='Note',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(blank=True, max_length=400)),
                ('player_name', models.CharField(max_length=80)),
                ('object_id', models.PositiveIntegerField(null=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('content_type', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
            ],
        ),
        migrations.CreateModel(
            name='Goalie',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('first_name', models.CharField(max_length=128)),
                ('last_name', models.CharField(max_length=128)),
                ('nhl_id', models.IntegerField(unique=True)),
                ('slug', models.SlugField()),
                ('image', models.ImageField(default='skater_default.png', storage=players.storage.OverwriteStorage(), upload_to='players_pics')),
                ('relevant_video', models.URLField(default='', max_length=128)),
                ('video_link_updated_at', models.DateField(default=datetime.date(2018, 10, 3))),
                ('position_abbr', models.CharField(max_length=128)),
                ('position_name', models.CharField(max_length=128)),
                ('height', models.CharField(max_length=128)),
                ('height_cm', models.IntegerField(null=True)),
                ('weight', models.IntegerField(null=True)),
                ('weight_kg', models.IntegerField(null=True)),
                ('birth_date', models.DateField()),
                ('birth_city', models.CharField(default='', max_length=128)),
                ('birth_state', models.CharField(default='', max_length=128)),
                ('birth_country', models.CharField(default='', max_length=128)),
                ('birth_country_abbr', models.CharField(default='', max_length=128)),
                ('nation', models.CharField(default='', max_length=128)),
                ('nation_abbr', models.CharField(blank=True, default='', max_length=128)),
                ('nation_flag', models.ImageField(default='flag.png', upload_to='flags')),
                ('draft_year', models.IntegerField(null=True)),
                ('draft_round', models.IntegerField(null=True)),
                ('draft_number', models.IntegerField(null=True)),
                ('pl_number', models.IntegerField(null=True)),
                ('age', models.IntegerField(null=True)),
                ('roster_status', models.CharField(max_length=128)),
                ('nhl_debut', models.CharField(max_length=12)),
                ('rookie', models.BooleanField(default=False)),
                ('captain', models.BooleanField(default=False)),
                ('alt_captain', models.BooleanField(default=False)),
                ('sbs_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('career_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('gamelog_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('games', models.IntegerField()),
                ('multiteams_seasons', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('seasons_count', models.IntegerField(null=True)),
                ('proj_stats', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('new_gamelog_stats', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('wins', models.IntegerField()),
                ('losses', models.IntegerField()),
                ('ot_losses', models.IntegerField()),
                ('goals_against_av', models.FloatField()),
                ('saves_perc', models.FloatField()),
                ('saves', models.IntegerField()),
                ('shotouts', models.IntegerField(default=0)),
                ('comparing', models.ManyToManyField(blank=True, related_name='comparable_goalies', to=settings.AUTH_USER_MODEL)),
                ('favoriting', models.ManyToManyField(blank=True, related_name='favorite_goalies', to=settings.AUTH_USER_MODEL)),
                ('team', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='goalies', to='players.Team')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Game',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nhl_id', models.IntegerField(unique=True)),
                ('slug', models.SlugField(max_length=128)),
                ('result', models.CharField(default='', max_length=128)),
                ('away_goalies', models.ManyToManyField(blank=True, related_name='goalie_away_games', to='players.Goalie')),
                ('away_skaters', models.ManyToManyField(blank=True, related_name='skater_away_games', to='players.Skater')),
                ('gameday', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='games', to='players.Gameday')),
                ('home_goalies', models.ManyToManyField(blank=True, related_name='goalie_home_games', to='players.Goalie')),
                ('home_skaters', models.ManyToManyField(blank=True, related_name='skater_home_games', to='players.Skater')),
                ('teams', models.ManyToManyField(blank=True, related_name='team_games', to='players.Team')),
            ],
        ),
    ]
