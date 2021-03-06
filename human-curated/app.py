from starlette.applications import Starlette
from starlette.responses import UJSONResponse

import uvicorn
import os
from sqlalchemy import engine, create_engine, MetaData, Table
from sqlalchemy.sql.expression import func, select
from random import uniform
import time
import tweepy

# Twitter app configuration information: required
CONSUMER_KEY = os.environ.get('CONSUMER_KEY')
CONSUMER_SECRET = os.environ.get('CONSUMER_SECRET')
ACCESS_KEY = os.environ.get('ACCESS_KEY')
ACCESS_SECRET = os.environ.get('ACCESS_SECRET')

assert all([CONSUMER_KEY, CONSUMER_SECRET, ACCESS_KEY, ACCESS_SECRET]
           ), "Not all Twitter app config tokens have been specified."

# Google Cloud SQL configuration information: required
ACCOUNT = os.environ.get("ACCOUNT")
DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")
DB_NAME = os.environ.get("DB_NAME")
CONNECTION_NAME = os.environ.get("CONNECTION_NAME")

# Request token: optional
REQUEST_TOKEN = os.environ.get('REQUEST_TOKEN', None)

app = Starlette(debug=False)

# Needed to avoid cross-domain issues
response_header = {
    'Access-Control-Allow-Origin': '*'
}


@app.route('/', methods=['GET', 'POST', 'HEAD'])
async def homepage(request):

    if request.method == 'GET':
        params = request.query_params
    elif request.method == 'POST':
        params = await request.json()
    elif request.method == 'HEAD':
        return UJSONResponse({'text': ''},
                             headers=response_header)

    # Validate request token
    if REQUEST_TOKEN and params.get('token') != REQUEST_TOKEN:
        return UJSONResponse({'text': 'Incorrect request token.'},
                             headers=response_header)

    db = create_engine(
        engine.url.URL(
            drivername='postgres+pg8000',
            username=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            query={
                'unix_sock': '/cloudsql/{}/.s.PGSQL.5432'.format(
                    CONNECTION_NAME)
            }
        ),
        pool_size=1
    )

    metadata = MetaData()
    tweets = Table('tweets', metadata, autoload=True,
                autoload_with=db)

    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)

    api = tweepy.API(auth)

    with db.connect() as conn:
        q = (
            select([tweets])
            .where(tweets.columns.account == ACCOUNT)
            .where(tweets.columns.tweet_timestamp == None)
            .order_by(func.random())
            .limit(1)
        )
        tweet = conn.execute(q).fetchone()

        if tweet is None:
            return UJSONResponse({'text': f"No more tweets left!"},
                                 headers=response_header)

        t = api.update_status(tweet.tweet)

        # Save record of tweet to prevent reuse
        t_timestamp = time.strftime("%Y-%m-%d %H:%M:%S+00", time.gmtime())
        t_url = f"https://twitter.com/{t.user.screen_name}/status/{t.id_str}"

        q_update = (
            tweets
            .update()
            .where(tweets.columns.id == tweet.id)
            .values(tweet_timestamp=t_timestamp,
                    tweet_url=t_url)
        )

        conn.execute(q_update)

    db.dispose()

    return UJSONResponse({'text': f"Tweet posted! {t_url}"},
                         headers=response_header)

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
