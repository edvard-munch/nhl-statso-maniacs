from . import utils

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import (GenericForeignKey,
                                                GenericRelation)
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField, JSONField
from django.db import models
from django.utils.text import slugify

from players.storage import OverwriteStorage


class Team(models.Model):
    name = models.CharField(max_length=128)
    nhl_id = models.IntegerField(unique=True)
    abbr = models.CharField(max_length=128)
    slug = models.SlugField()
    image = models.ImageField(upload_to='teams_logos', max_length=None,
                              storage=OverwriteStorage())
    arena_name = models.CharField(max_length=128)
    arena_location = models.CharField(max_length=128)
    division = models.CharField(max_length=128)
    conference = models.CharField(max_length=128)
    off_site = models.URLField(max_length=128)
    nhl_debut = models.CharField(max_length=128)

    def __str__(self):
        return f'{self.name}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            self.slug = slugify(self.name)
        super(Team, self).save(*args, **kwargs)

    def natural_key(self):
        return (self.abbr, self.name)


class Gameday(models.Model):
    day = models.DateField(unique=True, default=utils.get_default_date())

    def __str__(self):
        return f'{self.day}'


class Player(models.Model):
    name = models.CharField(max_length=128)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    nhl_id = models.IntegerField(unique=True)
    slug = models.SlugField()
    image = models.ImageField(upload_to='players_pics', default='skater_default.png',
                              max_length=None, storage=OverwriteStorage())
    relevant_video = models.URLField(max_length=128, default='')
    video_link_updated_at = models.DateField(default=utils.get_default_date())
    position_abbr = models.CharField(max_length=128)
    position_name = models.CharField(max_length=128)
    height = models.CharField(max_length=128)
    height_cm = models.IntegerField(null=True)
    weight = models.IntegerField(null=True)
    weight_kg = models.IntegerField(null=True)
    birth_date = models.DateField()
    birth_city = models.CharField(max_length=128, default='')
    birth_state = models.CharField(max_length=128, default='')
    birth_country = models.CharField(max_length=128, default='')
    birth_country_abbr = models.CharField(max_length=128, default='')
    nation = models.CharField(max_length=128, default='')
    nation_abbr = models.CharField(max_length=128, blank=True, default='')
    nation_flag = models.ImageField(upload_to='flags', default='flag.png')
    draft_year = models.IntegerField(null=True)
    draft_round = models.IntegerField(null=True)
    draft_number = models.IntegerField(null=True)
    pl_number = models.IntegerField(null=True)
    age = models.IntegerField(null=True)
    roster_status = models.CharField(max_length=128)
    nhl_debut = models.CharField(max_length=12)
    rookie = models.BooleanField(default=False)
    captain = models.BooleanField(default=False)
    alt_captain = models.BooleanField(default=False)
    sbs_stats = JSONField(null=True)
    career_stats = JSONField(null=True)
    gamelog_stats = JSONField(default=dict, blank=True)
    games = models.IntegerField()
    multiteams_seasons = JSONField(null=True)
    seasons_count = models.IntegerField(null=True)
    proj_stats = JSONField(null=True)
    note = GenericRelation('Note')

    def __str__(self):
        return f'{self.name}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            self.slug = slugify(self.name)
        super(Player, self).save(*args, **kwargs)

    class Meta:
        abstract = True


class Note(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.CharField(max_length=400, blank=True)
    player_name = models.CharField(max_length=80)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey()

    def __str__(self):
        return f'{self.author} about {self.player_name}'


class Position(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    data = ArrayField(models.CharField(max_length=5, blank=True), blank=True, default=list)
    player_name = models.CharField(max_length=80)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey()

    def __str__(self):
        return f'{self.author} positions for {self.player_name}'


class Skater(Player):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, related_name="skaters")
    favoriting = models.ManyToManyField(User, related_name='favorite_skaters', blank=True)
    comparing = models.ManyToManyField(User, related_name='comparable_skaters', blank=True)
    goals = models.IntegerField()
    goals_avg = models.FloatField()
    assists = models.IntegerField()
    assists_avg = models.FloatField()
    points = models.IntegerField()
    points_avg = models.FloatField()
    plus_minus = models.IntegerField()
    plus_minus_avg = models.FloatField()
    penalty_min = models.IntegerField()
    penalty_min_avg = models.FloatField()
    shots = models.IntegerField()
    shots_avg = models.FloatField()
    hits = models.IntegerField(null=True)
    hits_avg = models.FloatField(null=True)
    blocks = models.IntegerField(null=True)
    blocks_avg = models.FloatField(null=True)
    faceoff_wins = models.IntegerField(null=True)
    faceoff_wins_avg = models.FloatField(null=True)
    pp_points = models.IntegerField()
    pp_points_avg = models.FloatField()
    sh_points = models.IntegerField()
    sh_points_avg = models.FloatField()
    time_on_ice = models.CharField(max_length=128)
    time_on_ice_pp = models.CharField(max_length=128,)
    time_on_ice_sh = models.CharField(max_length=128)
    fw_stats = JSONField(default=dict, blank=True)
    sbs_stats_avg = JSONField(default=dict, blank=True)
    career_stats_avg = JSONField(default=dict, blank=True)


class Goalie(Player):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, related_name="goalies")
    favoriting = models.ManyToManyField(User, related_name='favorite_goalies', blank=True)
    comparing = models.ManyToManyField(User, related_name='comparable_goalies', blank=True)
    wins = models.IntegerField()
    losses = models.IntegerField()
    ot_losses = models.IntegerField()
    goals_against_av = models.FloatField()
    saves_perc = models.FloatField()
    saves = models.IntegerField()
    shotouts = models.IntegerField(default=0)


class Game(models.Model):
    teams = models.ManyToManyField(Team, related_name='team_games', blank=True, through='Side')
    nhl_id = models.IntegerField(unique=True)
    slug = models.SlugField(max_length=128)
    gameday = models.ForeignKey(Gameday, on_delete=models.CASCADE, null=True, related_name="games")
    result = models.CharField(max_length=128, default='')
    away_skaters = models.ManyToManyField(Skater, related_name='skater_away_games', blank=True)
    away_goalies = models.ManyToManyField(Goalie, related_name='goalie_away_games', blank=True)
    home_skaters = models.ManyToManyField(Skater, related_name='skater_home_games', blank=True)
    home_goalies = models.ManyToManyField(Goalie, related_name='goalie_home_games', blank=True)

    def __str__(self):
        return f'{self.gameday} - {self.side_set.get(side="away").team} - {self.side_set.get(side="home").team}'


class Side(models.Model):
    nhl_side_id = models.IntegerField(unique=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    side = models.CharField(max_length=128, default='')

    def __str__(self):
        return f'{self.team.name} as {self.side} side of {self.game.gameday.day} game'


def teams_list(game_obj):
    return list(game_obj.teams.all().values_list('name', flat=True))
