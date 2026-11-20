"""Every event goes to SQLite and (optionally) to every subscribed phone."""

import logging
import time

from . import db, push

log = logging.getLogger(__name__)


def add(kind, title, body="", notify=True):
    ts = int(time.time())
    db.execute("INSERT INTO events(ts, kind, title, body, pushed) VALUES(?,?,?,?,?)",
               (ts, kind, title, body, 1 if notify else 0))
    log.info("EVENT [%s] %s %s", kind, title, body)
    if notify:
        push.queue_push(title, body, tag=kind)


def recent(limit=100, before_id=None, kind=None):
    sql = "SELECT id, ts, kind, title, body FROM events"
    where, params = [], []
    if before_id:
        where.append("id < ?")
        params.append(before_id)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)
