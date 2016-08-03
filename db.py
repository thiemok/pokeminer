from datetime import datetime
import json
import time

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.sql import not_


with open('locales/pokemon.en.json') as f:
    pokemon_names = json.load(f)


try:
    import config
    DB_ENGINE = config.DB_ENGINE
except (ImportError, AttributeError):
    DB_ENGINE = 'sqlite:///db.sqlite'


def get_engine():
    return create_engine(DB_ENGINE)


def get_engine_name(session):
    return session.connection().engine.name


Base = declarative_base()


class SightingCache(object):
    """Simple cache for storing actual sightings

    It's used in order not to make as many queries to the database.
    It's also capable of purging old entries.
    """
    def __init__(self):
        self.store = {}

    @staticmethod
    def _make_key(sighting):
        return (
            sighting.pokemon_id,
            sighting.spawn_id,
            sighting.normalized_timestamp,
            sighting.lat,
            sighting.lon,
        )

    def add(self, sighting):
        self.store[self._make_key(sighting)] = sighting.expire_timestamp

    def __contains__(self, sighting):
        expire_timestamp = self.store.get(self._make_key(sighting))
        if not expire_timestamp:
            return False
        timestamp_in_range = (
            expire_timestamp > sighting.expire_timestamp - 5 and
            expire_timestamp < sighting.expire_timestamp + 5
        )
        return timestamp_in_range

    def clean_expired(self):
        to_remove = []
        for key, timestamp in self.store.items():
            if timestamp < time.time() - 120:
                to_remove.append(key)
        for key in to_remove:
            del self.store[key]

CACHE = SightingCache()


class Sighting(Base):
    __tablename__ = 'sightings'

    id = Column(Integer, primary_key=True)
    pokemon_id = Column(Integer)
    spawn_id = Column(String(32))
    expire_timestamp = Column(Integer)
    normalized_timestamp = Column(Integer)
    lat = Column(String(16))
    lon = Column(String(16))


Session = sessionmaker(bind=get_engine())


def normalize_timestamp(timestamp):
    return int(float(timestamp) / 120.0) * 120


def get_since():
    """Returns 'since' timestamp that should be used for filtering"""
    return time.mktime(config.REPORT_SINCE.timetuple())


def get_since_query_part(where=True):
    """Returns WHERE part of query filtering records before set date"""
    if config.REPORT_SINCE:
        return '{noun} expire_timestamp > {since}'.format(
            noun='WHERE' if where else 'AND',
            since=get_since(),
        )
    return ''


def add_sighting(session, pokemon):
    obj = Sighting(
        pokemon_id=pokemon['pokemon_id'],
        spawn_id=pokemon['spawn_id'],
        expire_timestamp=pokemon['expire_timestamp'],
        normalized_timestamp=normalize_timestamp(pokemon['expire_timestamp']),
        lat=pokemon['lat'],
        lon=pokemon['lon'],
    )
    # Check if there isn't the same entry already
    if obj in CACHE:
        return
    existing = session.query(Sighting) \
        .filter(Sighting.pokemon_id == obj.pokemon_id) \
        .filter(Sighting.spawn_id == obj.spawn_id) \
        .filter(Sighting.expire_timestamp > obj.expire_timestamp - 10) \
        .filter(Sighting.expire_timestamp < obj.expire_timestamp + 10) \
        .filter(Sighting.lat == obj.lat) \
        .filter(Sighting.lon == obj.lon) \
        .first()
    if existing:
        return
    session.add(obj)
    CACHE.add(obj)


def get_sightings(session):
    query = session.query(Sighting) \
        .filter(Sighting.expire_timestamp > time.time())
    trash_list = getattr(config, 'TRASH_IDS', None)
    if trash_list:
        query = query.filter(not_(Sighting.pokemon_id.in_(config.TRASH_IDS)))
    return query.all()


def get_session_stats(session):
    query = '''
        SELECT
            MIN(expire_timestamp) ts_min,
            MAX(expire_timestamp) ts_max,
            COUNT(*)
        FROM `sightings`
        {report_since}
    '''
    min_max_query = session.execute(query.format(
        report_since=get_since_query_part()
    ))
    min_max_result = min_max_query.first()
    length_hours = (min_max_result[1] - min_max_result[0]) // 3600
    if length_hours == 0:
        length_hours = 1
    # Convert to datetime
    return {
        'start': datetime.fromtimestamp(min_max_result[0]),
        'end': datetime.fromtimestamp(min_max_result[1]),
        'count': min_max_result[2],
        'length_hours': length_hours,
        'per_hour': min_max_result[2] / length_hours,
    }


def get_punch_card(session):
    if get_engine_name(session) == 'sqlite':
        bigint = 'BIGINT'
    else:
        bigint = 'UNSIGNED'
    query = session.execute('''
        SELECT
            CAST((expire_timestamp / 300) AS {bigint}) ts_date,
            COUNT(*) how_many
        FROM `sightings`
        {report_since}
        GROUP BY ts_date
        ORDER BY ts_date
    '''.format(bigint=bigint, report_since=get_since_query_part()))
    results = query.fetchall()
    results_dict = {r[0]: r[1] for r in results}
    filled = []
    for row_no, i in enumerate(range(int(results[0][0]), int(results[-1][0]))):
        item = results_dict.get(i)
        filled.append((row_no, item if item else 0))
    return filled


def get_top_pokemon(session, count=30, order='DESC'):
    query = session.execute('''
        SELECT
            pokemon_id,
            COUNT(*) how_many
        FROM sightings
        {report_since}
        GROUP BY pokemon_id
        ORDER BY how_many {order}
        LIMIT {count}
    '''.format(order=order, count=count, report_since=get_since_query_part()))
    return query.fetchall()


def get_stage2_pokemon(session):
    result = []
    if not hasattr(config, 'STAGE2'):
        return []
    for pokemon_id in config.STAGE2:
        query = session.query(Sighting) \
            .filter(Sighting.pokemon_id == pokemon_id)
        if config.REPORT_SINCE:
            query = query.filter(Sighting.expire_timestamp > get_since())
        count = query.count()
        if count > 0:
            result.append((pokemon_id, count))
    return result


def get_nonexistent_pokemon(session):
    result = []
    query = session.execute('''
        SELECT DISTINCT pokemon_id FROM sightings
        {report_since}
    '''.format(report_since=get_since_query_part()))
    db_ids = [r[0] for r in query.fetchall()]
    for pokemon_id in range(1, 152):
        if pokemon_id not in db_ids:
            result.append(pokemon_id)
    return result


def get_all_sightings(session, pokemon_ids):
    # TODO: rename this and get_sightings
    query = session.query(Sighting) \
        .filter(Sighting.pokemon_id.in_(pokemon_ids))
    if config.REPORT_SINCE:
        query = query.filter(Sighting.expire_timestamp > get_since())
    return query.all()


def get_spawns_per_hour(session, pokemon_id):
    if get_engine_name(session) == 'sqlite':
        ts_hour = 'STRFTIME("%H", expire_timestamp)'
    else:
        ts_hour = 'HOUR(FROM_UNIXTIME(expire_timestamp))'
    query = session.execute('''
        SELECT
            {ts_hour} AS ts_hour,
            COUNT(*) AS how_many
        FROM sightings
        WHERE pokemon_id = {pokemon_id}
        {report_since}
        GROUP BY ts_hour
        ORDER BY ts_hour
    '''.format(
        pokemon_id=pokemon_id,
        ts_hour=ts_hour,
        report_since=get_since_query_part(where=False)
    ))
    results = []
    for result in query.fetchall():
        results.append((
            {
                'v': [int(result[0]), 30, 0],
                'f': '{}:00 - {}:00'.format(
                    int(result[0]), int(result[0]) + 1
                ),
            },
            result[1]
        ))
    return results


def get_total_spawns_count(session, pokemon_id):
    query = session.execute('''
        SELECT COUNT(id)
        FROM sightings
        WHERE pokemon_id = {pokemon_id}
        {report_since}
    '''.format(
        pokemon_id=pokemon_id,
        report_since=get_since_query_part(where=False)
    ))
    result = query.first()
    return result[0]


def get_all_spawn_coords(session, pokemon_id=None):
    points = session.query(Sighting.lat, Sighting.lon)
    if pokemon_id:
        points = points.filter(Sighting.pokemon_id == int(pokemon_id))
    if config.REPORT_SINCE:
        points = points.filter(Sighting.expire_timestamp > get_since())
    return points.all()
