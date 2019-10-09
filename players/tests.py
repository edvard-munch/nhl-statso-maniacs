import unittest
from unittest.mock import patch
from django.test import TestCase
from django.test import SimpleTestCase
from django.urls import reverse
from django.test import Client

from . import utils
from .models import Skater, Goalie, Team


# class utilsDBTests(unittest.TestCase):
#     def test_get_player(self):
#         self.assertEqual(utils.get_player(8475913, 'mark-stone').name, 'Mark Stone')
#         self.assertIsNone(utils.get_player(8475913, 'mark-ston'))
#         self.assertIsNone(utils.get_player(847591, 'mark-stone'))
#         self.assertIsNone(utils.get_player(847591, 'mark-ston'))
#
#     # @patch('players.models.Skater.objects')
#     @patch('players.utils.get_player')
#     def test_patched_get_player(self, mock_get_player):
#         mock_get_player.return_value = 'Mark Stone'
#         self.assertEqual(utils.get_player(8475913, 'mark-stone'), 'Mark Stone')
#
#         mock_get_player.return_value = None
#         self.assertIsNone(utils.get_player(8475913, 'mark-ston'))
#
#         mock_get_player.return_value = None
#         self.assertIsNone(utils.get_player(847591, 'mark-stone'))
#
#         mock_get_player.return_value = None
#         self.assertIsNone(utils.get_player(847591, 'mark-ston'))

# about
# home
# skaters_averages
# favorites
# player_gamelog
# player_note
# player_positions
# player_favorite
# team_detail
# autocompleteModel


# players Integration
# class ViewsTests(TestCase):
#     def test_players_view(self):
#         response = self.client.get(reverse('players'))
#         self.assertEqual(response.status_code, 200)
#
#     def test_search_view(self):
#         response = self.client.get(reverse('search'))
#         self.assertEqual(response.status_code, 200)


class ViewsDBTests(unittest.TestCase):
    # # player_detail Integration
    def test_player_detail_view(self):
        rand_players = [Skater.objects.random(), Goalie.objects.random()]
        client = Client()
        for player in rand_players:
            response = client.get(reverse('player_detail', args=(player.slug, player.nhl_id)))
            self.assertEqual(response.context['player'].name, player.name)


    def test_team_detail_view(self):
        rand_team = Team.objects.random()
        client = Client()
        response = client.get(reverse('team_detail', args=(rand_team.slug, rand_team.nhl_id)))
        self.assertEqual(response.context['team'].name, rand_team.name)
#
#
# class utilsTests(SimpleTestCase):
#     def test_time_from_sec(self):
#         self.assertEqual(utils.time_from_sec(456546), '7609:06')
#         self.assertIsInstance(utils.time_from_sec(456546), str)
