import datetime
import json
import os
import random
import webbrowser
from itertools import chain
from pathlib import Path

import furl
import googleapiclient.discovery
import googleapiclient.errors
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from googleapiclient.errors import HttpError
from oauth2client import client
from oauth2client.file import Storage
from tqdm import tqdm

from players.models import Goalie, Skater

API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
BASE_YT_URL = 'https://www.youtube.com/embed/'
REDIRECT_URI = 'http://127.0.0.1:8000/auth_callback/'
SEARCH_PARAMS = {
    'part': 'snippet',
    'content_type': 'video',
    'fields': 'items/id/videoId',
    'relevance_language': 'en',
    'region_code': 'us',
    'video_embeddable': 'true',
    'max_results': 1,
}
CREDENTIALS_FOLDER = 'credentials'
CLIENT_SECRET_FILES = [f'client_secret-{index}.json' for index in range(1, 12)]
CREDENTIAL_FILES = [f'credentials-{index}.json' for index in range(1, 12)]
DAILY_LIMIT = ['dailyLimitExceeded', 'quotaExceeded']
TIME_AGO = {
    'months': 6,
}
LINK_UPDATE_TIME = 30
ZULU_TIMEZONE = 'Z'


class Command(BaseCommand):
    def handle(self, *args, **options):
        players = tuple(chain(Goalie.objects.all(), Skater.objects.all()))
        for player in tqdm(players):
            if link_old_or_missing(player):
                while CREDENTIAL_FILES:
                    link = get_link(player.name)
                    if link:
                        player.relevant_video = link
                        player.video_link_updated_at = datetime.datetime.now()
                        player.save(update_fields=['relevant_video', 'video_link_updated_at'])
                        print(f'{player.name} link is updated!')
                        break
                    else:
                        print(f'{player.name} link could not be updated with these credentials!')
            else:
                print(f'{player.name} link is up do date!')


def link_old_or_missing(player):
    if not player.relevant_video:
        return True

    diff = datetime.date.today() - player.video_link_updated_at
    return diff.days > LINK_UPDATE_TIME


def get_storage(*index):
    if index:
        credentials_file = CREDENTIAL_FILES[index[0]]
    else:
        credentials_file = random.choice(CREDENTIAL_FILES)
        index = CREDENTIAL_FILES.index(credentials_file)

    credential_path = os.path.join(get_current_folder(), CREDENTIALS_FOLDER, credentials_file)
    return (Storage(credential_path), index)


def get_current_folder():
    return Path(__file__).parent.absolute()


def get_new_credentials(index):
    secrets_file = os.path.join(get_current_folder(), CREDENTIALS_FOLDER, CLIENT_SECRET_FILES[index])
    flow = client.flow_from_clientsecrets(secrets_file, SCOPES, redirect_uri=REDIRECT_URI)
    auth_url = flow.step1_get_authorize_url()
    webbrowser.open(auth_url)
    url = input('Insert URL with code:\n')
    code = furl.furl(url).args.get('code', '')
    return flow.step2_exchange(code)


def credentials_valid(credentials):
    return credentials and not credentials.invalid


def get_link(full_name):
    credentials, index = get_storage()
    credentials = credentials.get()
    if not credentials_valid(credentials):
        credentials = get_new_credentials(index)
        get_storage(index)[0].put(credentials)

    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials)

    request = youtube.search().list(
        part=SEARCH_PARAMS['part'],
        fields=SEARCH_PARAMS['fields'],
        q=full_name,
        type=SEARCH_PARAMS['content_type'],
        maxResults=SEARCH_PARAMS['max_results'],
        publishedAfter=published_after(),
        videoEmbeddable=SEARCH_PARAMS['video_embeddable'],
        relevanceLanguage=SEARCH_PARAMS['relevance_language'],
        regionCode=SEARCH_PARAMS['region_code'],
    )

    try:
        response = request.execute()
        print(BASE_YT_URL + response['items'][0]['id']['videoId'])
        print(f'{CREDENTIAL_FILES[index]} used successfullly!')
        return BASE_YT_URL + response['items'][0]['id']['videoId']
    except HttpError:
        data = json.loads(HttpError.content.decode('utf-8'))
        reason = data['error']['errors'][0]['reason']
        if reason in DAILY_LIMIT:
            print(f'{CREDENTIAL_FILES[index]} quota is exceeded!')
            del CREDENTIAL_FILES[index]
            del CLIENT_SECRET_FILES[index]
        return None


# Need to add Zulu timezone symbol because it doesn't work with just isoformat()
def published_after():
    date_now = datetime.datetime.now()
    return (date_now - relativedelta(**TIME_AGO)).isoformat() + ZULU_TIMEZONE
