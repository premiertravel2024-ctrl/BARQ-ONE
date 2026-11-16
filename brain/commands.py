"""Durable command intake, separate from tool execution and approval tokens."""
import hashlib,json,time,uuid
from core.sqlite import connect
from coding.redaction import redact


class CommandStore:
    def __init__(self,path):
        self.path=path
        with connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS brain_commands (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, signature TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL, UNIQUE(conversation_id,signature))')

    def get(self,command_id,conversation_id):
        with connect(self.path) as db:
            row=db.execute('SELECT conversation_id,data FROM brain_commands WHERE id=?',(command_id,)).fetchone()
        if not row:raise ValueError('Saved command not found')
        if row[0]!=conversation_id:raise ValueError('This command belongs to another conversation')
        return json.loads(row[1])

    def begin(self,conversation_id,messages,workspace,model,local_only=False):
        signature=hashlib.sha256(json.dumps([messages,workspace,model],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        safe=[{'role':m['role'],'content':redact(str(m.get('content','')))[:12000]} for m in messages[-24:]]
        item={'id':uuid.uuid4().hex,'conversation_id':conversation_id,'messages':safe,'workspace':workspace,
            'model':model,'local_only':local_only,'status':'understanding','intent':None,'diagnostic':None,'updated':time.time()}
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT data FROM brain_commands WHERE conversation_id=? AND signature=?',(conversation_id,signature)).fetchone()
            if previous and json.loads(previous[0])['status']=='cancelled':signature+=':'+item['id']
            db.execute('INSERT OR IGNORE INTO brain_commands VALUES (?,?,?,?,?)',
                (item['id'],conversation_id,signature,json.dumps(item,ensure_ascii=False),item['updated']))
            row=db.execute('SELECT data FROM brain_commands WHERE conversation_id=? AND signature=?',(conversation_id,signature)).fetchone()
        return json.loads(row[0])

    def update(self,command_id,conversation_id,**patch):
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT conversation_id,data FROM brain_commands WHERE id=?',(command_id,)).fetchone()
            if not row:raise ValueError('Saved command not found')
            if row[0]!=conversation_id:raise ValueError('This command belongs to another conversation')
            item={**json.loads(row[1]),**patch,'updated':time.time()}
            db.execute('UPDATE brain_commands SET data=?,updated=? WHERE id=?',
                (json.dumps(item,ensure_ascii=False),item['updated'],command_id))
        return item

    def waiting(self,conversation_id):
        with connect(self.path) as db:
            rows=db.execute('SELECT data FROM brain_commands WHERE conversation_id=? ORDER BY updated DESC LIMIT 30',(conversation_id,)).fetchall()
        return next((item for row in rows if (item:=json.loads(row[0]))['status']=='waiting_model'),None)

    def cancel_waiting(self,conversation_id):
        changed=False
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT id,data FROM brain_commands WHERE conversation_id=?',(conversation_id,)).fetchall()
            for command_id,data in rows:
                item=json.loads(data)
                if item['status'] in {'chat','cancelled'}:continue
                item={**item,'status':'cancelled','updated':time.time()}
                db.execute('UPDATE brain_commands SET data=?,updated=? WHERE id=?',(json.dumps(item,ensure_ascii=False),item['updated'],command_id))
                changed=True
        return changed


def public_pending(item):
    user=next((m['content'] for m in reversed(item['messages']) if m['role']=='user'),'')
    return {'id':item['id'],'status':item['status'],'goal':user[:12000],
        'diagnostic':item.get('diagnostic')}
