cd programming/py/nhl_web_app
source venv/bin/activate
django r

Super + T
Host(right Ctrl) + Alt + Tab

source venv/bin/activate
python3 -m venv venv

git status
git diff / git diff --cached
git add .
git commit -am "MESSAGE"
git checkout -b 'BRANCH_NAME'
git branch -d 'BRANCH_NAME'
git push -u nhl_web_app master
git pull nhl_web_app master
git citool
git fsck - Verifies the connectivity and validity of the objects in the database

gedit ~/.profile
ENV_VAR=value
gnome-tweaks

git config --global credential.helper "cache --timeout=3600"
git config --global credential.helper store

cd programming/py/nhl_web_app
celery -A nhl_web_app worker -l info -P gevent

cd programming\py\nhl_web_app
django s
from players.tasks import upd_pls
upd_pls.delay()

sudo -u postgres psql
sudo -u postgres createuser owning_user / sudo -u postgres createuser arkadiy-dev
sudo -u postgres createuser arkadiy-dev / CREATE USER youruser WITH ENCRYPTED PASSWORD 'yourpass';
alter user arkadiy-dev with encrypted password "ark085075"  /  ALTER USER "arkadiy-dev" WITH PASSWORD 'ark085075';
create database nhl_web_app_19_20 / CREATE DATABASE yourdbname;
grant all privileges on database "nhl_web_app_19_20" to "arkadiy-dev"; / GRANT ALL PRIVILEGES ON DATABASE yourdbname TO youruser;

pyment [PATH or FILE] -o google -w