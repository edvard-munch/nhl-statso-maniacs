from django.contrib import admin

from .models import Goalie, Skater, Team, Note, Position, Game, Gameday, Side


class GoalieAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


class SkaterAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}
    list_per_page = 1000


class TeamAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


class NoteAdmin(admin.ModelAdmin):
    pass


class SideAdmin(admin.ModelAdmin):
    pass


class PositionAdmin(admin.ModelAdmin):
    pass


class GameAdmin(admin.ModelAdmin):
    list_per_page = 100


class GamedayAdmin(admin.ModelAdmin):
    list_per_page = 200


admin.site.register(Goalie, GoalieAdmin)
admin.site.register(Skater, SkaterAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(Note, NoteAdmin)
admin.site.register(Position, PositionAdmin)
admin.site.register(Game, GameAdmin)
admin.site.register(Gameday, GamedayAdmin)
admin.site.register(Side, SideAdmin)
