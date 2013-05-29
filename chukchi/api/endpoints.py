# This file is part of Chukchi, the free web-based RSS aggregator
#
#   Copyright (C) 2013 Edward Toroshchin <chukchi-project@hades.name>
#
# Chukchi is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Chukchi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# Please see the file COPYING in the root directory of this project.
# If you are unable to locate this file, see <http://www.gnu.org/licenses/>.

import logging

from functools import wraps

from flask import abort, g, request, session

from . import app, db, needs_session
from ..db.models import Content, Entry, Subscription, Unread, User

LOG = logging.getLogger(__name__)

MAX_ENTRY_COUNT = 500

@app.errorhandler(KeyError)
def no_key(e):
    return {'error': 400,
            'message': 'A field was missing from the request'}, 400

@app.route('/content/<int:content_id>', methods=('GET',))
@needs_session
def content(content_id):
    content = db.query(Content).filter_by(id=content_id).first()
    if not content:
        abort(404)
    result = content.to_json()
    result['data'] = content.data
    return result

def query_entries(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        start = int(request.args.get('start', 0))
        count = min(int(request.args.get('count', MAX_ENTRY_COUNT)), MAX_ENTRY_COUNT)
        unread = bool(request.args.get('unread', False))

        query = f(*args, **kwargs)
        if unread:
            query = query.join(Unread, (Entry.id == Unread.entry_id) &\
                                       (Unread.user_id == g.user.id))
        else:
            query = query.join(Subscription, (Entry.feed_id == Subscription.feed_id) &\
                                             (Subscription.user_id == g.user.id))
        query = query.order_by(Entry.id.desc())
        LOG.debug("query_entries f==%r unread==%s SQL: %s", f, unread, query.statement)
        total = query.count()
        if start:
            query = query.filter(Entry.id < start)
        query = query.limit(count)
        return {'total': total,
                'entries': [e.to_json() for e in query]}
    return wrapped

@app.route('/entries', methods=('GET',))
@needs_session
@query_entries
def get_all_entries():
    return db.query(Entry)

@app.route('/entries/<int:feed_id>', methods=('GET',))
@needs_session
@query_entries
def get_feed_entries(feed_id):
    return db.query(Entry).filter_by(feed_id=feed_id)

@app.route('/session', methods=('GET', 'DELETE'))
@needs_session
def get_delete_session():
    if request.method == 'DELETE':
        session.clear()
        return {}
    return {'user': g.user.id}

@app.route('/subscriptions', methods=('GET',))
@needs_session
def subscriptions():
    result = {'data': []}
    for s in g.user.subscriptions:
        sj = s.to_json()
        sj['unread_count'] = db.query(Entry)\
                               .filter_by(feed=s.feed)\
                               .join(Unread, (Entry.id == Unread.entry_id) &\
                                             (Unread.user_id == g.user.id))\
                               .count()
        result['data'].append(sj)
    return result

@app.route('/unread/<int:entry_id>', methods=('PUT', 'DELETE',))
@needs_session
def unread(entry_id):
    entry = db.query(Entry).filter_by(id=entry_id).first()
    if not entry:
        abort(404)
    unread_obj = db.query(Unread).filter_by(entry=entry, user=g.user).first()
    if request.method == 'PUT' and not unread_obj:
        db.add(Unread(entry=entry, user=g.user))
    elif request.method == 'DELETE' and unread_obj:
        db.delete(unread_obj)
    db.commit()
    return {}

# vi: sw=4:ts=4:et
