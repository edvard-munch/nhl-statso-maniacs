python3 -m venv venv
source venv/bin/activate
git commit -am

sudo -u postgres psql
sudo -u postgres createuser owning_user


d:
cd programming\py\nhl_web_app
django r


d:
cd programming\py\nhl_web_app
celery -A nhl_web_app worker -l info -P gevent


cd programming\py\nhl_web_app
django s
from players.tasks import upd_pls
upd_pls.delay()

cd programming\py\nhl_web_app
git push heroku master
heroku logs -t


git fsck - Verifies the connectivity and validity of the objects in the database
git push -u nhl_web_app master
git pull nhl_web_app master
