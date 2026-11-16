from __future__ import annotations
from core.sqlite import connect as barq_sqlite_connect
import sqlite3,json,time,uuid
from core.paths import state_file

class ConversationStore:
    def __init__(self,db_path=None):
        self.db_path=str(db_path or state_file('conversations.sqlite3'))
        with self.connect() as db:
            db.execute('create table if not exists conversations (id text primary key, title text not null, messages text not null, updated real not null)')
    def connect(self):
        return barq_sqlite_connect(self.db_path,timeout=10)
    def list(self):
        with self.connect() as db:
            return [{'id':id,'title':title,'updated':updated} for id,title,updated in db.execute('select id,title,updated from conversations order by updated desc limit 150')]
    def list_titles(self,limit:int=35):
        """Read only chat identifiers, titles and last edit time; no message bodies."""
        size=max(1,min(int(limit),50))
        with self.connect() as db:
            return [{'id':cid,'title':title[:120],'updated':updated}
                    for cid,title,updated in db.execute('SELECT id,title,updated FROM conversations ORDER BY updated DESC LIMIT ?', (size,))]

    def get(self,id):
        with self.connect() as db:
            row=db.execute('select title,messages from conversations where id=?',(id,)).fetchone()
        if row is None:raise ValueError('Conversation not found')
        return {'id':id,'title':row[0],'messages':json.loads(row[1])}
    def put(self,id,title,messages):
        if len(messages)>150:raise ValueError('Conversation too large')
        if len(json.dumps(messages,ensure_ascii=False))>800_000:raise ValueError('Conversation exceeds storage limits')
        if not id or len(id)>80:raise ValueError('Invalid ID')
        with self.connect() as db:
            db.execute('insert or replace into conversations values (?,?,?,?)',(id,title[:160],json.dumps(messages,ensure_ascii=False),time.time()))
    def delete(self,id):
        with self.connect() as db:db.execute('delete from conversations where id=?',(id,))

    def search(self, query: str, limit: int = 5, exclude_id: str = '') -> list[dict]:
        """Search own saved conversations, bounded and with no attachment exposure."""
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 100:
            return []
        needle = query.strip().casefold()
        words = [word for word in needle.split() if len(word) > 1]
        if not words:
            words = [needle]
        matches = []
        # Stream the saved archive, not just the 150 most recent sidebar items.
        # Stop once enough matches exist, avoiding bulk export of old chat JSON.
        with self.connect() as db:
            rows = db.execute('select id,title,messages,updated from conversations order by updated desc')
            for cid, title, raw, updated in rows:
                if cid == exclude_id:
                    continue
                try:
                    messages = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(messages, list):
                    continue
                # Only text messages; ignore attachment payloads and metadata.
                text_parts = [m.get('content', '')[:1500] for m in messages[-100:]
                              if isinstance(m, dict) and m.get('role') in ('user','assistant')
                              and isinstance(m.get('content'), str)]
                title_matches = all(w in title.casefold() for w in words)
                matching = next((part for part in reversed(text_parts)
                                 if all(w in part.casefold() for w in words)), '')
                if title_matches or matching:
                    matches.append({'id':cid, 'title':title,
                                    'excerpt':matching[:220] if matching else '', 'updated':updated})
                    if len(matches) >= max(1, min(limit, 5)):
                        break
        return matches
