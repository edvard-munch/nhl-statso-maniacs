from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import (GenericForeignKey,
                                                GenericRelation)
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField, JSONField
from django.db import models
from django.utils.text import slugify
from players.storage import OverwriteStorage
import datetime


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
    day = models.DateField(unique=True, default=datetime.date.today)
    all_games_finished = models.BooleanField(default=False)
    all_games_uploaded = models.BooleanField(default=False)

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
    video_link_updated_at = models.DateField(default=datetime.date.today)
    position_abbr = models.CharField(max_length=128, blank=True)
    position_name = models.CharField(max_length=128, blank=True)
    height = models.CharField(max_length=128, blank=True)
    height_cm = models.IntegerField(null=True)
    weight = models.IntegerField(null=True)
    weight_kg = models.IntegerField(null=True)
    birth_date = models.DateField()
    birth_city = models.CharField(max_length=128, blank=True)
    birth_state = models.CharField(max_length=128, blank=True)
    birth_country = models.CharField(max_length=128, blank=True)
    birth_country_abbr = models.CharField(max_length=128, blank=True)
    nation = models.CharField(max_length=128, blank=True)
    nation_abbr = models.CharField(max_length=128, blank=True,)
    nation_flag = models.ImageField(upload_to='flags', default='flag.png')
    draft_year = models.IntegerField(null=True)
    draft_round = models.IntegerField(null=True)
    draft_number = models.IntegerField(null=True)
    pl_number = models.IntegerField(null=True)
    age = models.IntegerField(null=True)
    roster_status = models.CharField(max_length=128, blank=True)
    nhl_debut = models.CharField(max_length=12, blank=True)
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
        return f'{self.name} - {self.nhl_id}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        no_slug = not self.slug

        if is_new or no_slug:
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
    goals = models.IntegerField(null=True)
    goals_avg = models.FloatField(null=True)
    assists = models.IntegerField(null=True)
    assists_avg = models.FloatField(null=True)
    points = models.IntegerField(null=True)
    points_avg = models.FloatField(null=True)
    plus_minus = models.IntegerField(null=True)
    plus_minus_avg = models.FloatField(null=True)
    penalty_min = models.IntegerField(null=True)
    penalty_min_avg = models.FloatField(null=True)
    shots = models.IntegerField(null=True)
    shots_avg = models.FloatField(null=True)
    hits = models.IntegerField(null=True)
    hits_avg = models.FloatField(null=True)
    blocks = models.IntegerField(null=True)
    blocks_avg = models.FloatField(null=True)
    faceoff_wins = models.IntegerField(null=True)
    faceoff_wins_avg = models.FloatField(null=True)
    pp_points = models.IntegerField(null=True)
    pp_points_avg = models.FloatField(null=True)
    sh_points = models.IntegerField(null=True)
    sh_points_avg = models.FloatField(null=True)
    time_on_ice = models.CharField(max_length=128)
    time_on_ice_pp = models.CharField(max_length=128)
    time_on_ice_sh = models.CharField(max_length=128)
    fw_stats = JSONField(default=dict, blank=True)
    sbs_stats_avg = JSONField(default=dict, blank=True)
    career_stats_avg = JSONField(default=dict, blank=True)


class Goalie(Player):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, related_name="goalies")
    favoriting = models.ManyToManyField(User, related_name='favorite_goalies', blank=True)
    comparing = models.ManyToManyField(User, related_name='comparable_goalies', blank=True)
    wins = models.IntegerField(null=True)
    losses = models.IntegerField(null=True)
    ot_losses = models.IntegerField(null=True)
    goals_against_av = models.FloatField(null=True)
    saves_perc = models.FloatField(null=True)
    saves = models.IntegerField(null=True)
    shotouts = models.IntegerField(default=0)


class Game(models.Model):
    teams = models.ManyToManyField(Team, related_name='team_games', blank=True, through='Side')
    nhl_id = models.IntegerField(unique=True)
    slug = models.SlugField(max_length=128)
    game_finished = models.BooleanField(default=False)
    gameday = models.ForeignKey(Gameday, on_delete=models.CASCADE, null=True, related_name="games")
    result = models.CharField(max_length=128, default='')

    away_defencemen = models.ManyToManyField(Skater, related_name='defencemen_away_games', blank=True)
    away_forwards = models.ManyToManyField(Skater, related_name='forwards_away_games', blank=True)
    away_goalies = models.ManyToManyField(Goalie, related_name='goalie_away_games', blank=True)

    home_defencemen = models.ManyToManyField(Skater, related_name='defencemen_home_games', blank=True)
    home_forwards = models.ManyToManyField(Skater, related_name='forwards_home_games', blank=True)
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
