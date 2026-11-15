"""Human-facing vocabulary, with execution truth computed exclusively from state."""
import hashlib
import json
from pathlib import Path

ROLES = {'generator': 'Construcción', 'ux': 'Diseño', 'requirements': 'Planificación',
         'reviewer': 'Verificación', 'ux_review': 'Revisión visual', 'security': 'Seguridad', 'recovery': 'Resolución'}
ACTIVE = {'running', 'starting', 'pending', 'launching'}

def brief(state):
    return {'objective': state['request'].get('objective', '')[:6000],
            'units': [{k: u.get(k) for k in ('id', 'owner', 'objective', 'acceptance', 'depends_on')} for u in state.get('units', [])]}

def fingerprint(state):
    return hashlib.sha256(json.dumps(brief(state), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def validate(copy, state):
    ids = {u['id'] for u in state.get('units', [])}
    if set(copy) != {'name', 'purpose', 'tasks', 'capabilities'}: raise ValueError('Unexpected narrative fields')
    def short(value, limit):
        if not isinstance(value, str) or not value.strip() or len(value) > limit: raise ValueError('Invalid copy')
        if any(x in value for x in ['http://', 'https://', '/home/', '```']): raise ValueError('Technical content')
    short(copy['name'], 70); short(copy['purpose'], 180)
    if len(copy['tasks']) != len(ids) or {x['id'] for x in copy['tasks']} != ids: raise ValueError('Task coverage')
    for task in copy['tasks']:
        if set(task) != {'id', 'title', 'purpose', 'outcome'}: raise ValueError('Task shape')
        short(task['title'], 70); short(task['purpose'], 180); short(task['outcome'], 180)
    if not 1 <= len(copy['capabilities']) <= 16: raise ValueError('Capabilities bounds')
    coverage = set()
    for c in copy['capabilities']:
        if set(c) != {'title', 'purpose', 'units'}: raise ValueError('Capability shape')
        short(c['title'], 70); short(c['purpose'], 180)
        if not c['units'] or not set(c['units']) <= ids: raise ValueError('Capability mapping')
        coverage.update(c['units'])
    if coverage != ids: raise ValueError('Capability coverage')
    return copy

def presentation(state, root):
    record = {}; copy = None
    path = Path(root) / 'communication' / (state['id'] + '.json')
    try:
        if path.stat().st_size > 500000: raise ValueError('Oversized communication')
        record = json.loads(path.read_text())
        if record.get('fingerprint') == fingerprint(state): copy = validate(record['copy'], state)
    except (OSError, ValueError, KeyError, TypeError): pass
    tasks = {x['id']: x for x in copy['tasks']} if copy else {}
    units = state.get('units', []); by_id = {u['id']: u for u in units}
    def status(unit):
        if unit.get('state') == 'accepted': return 'verified'
        jobs = [j for j in state.get('jobs', []) if j.get('unit') == unit['id'] and j.get('status') in ACTIVE]
        if jobs: return 'reviewing' if all(j.get('role') in {'reviewer','ux_review','security'} for j in jobs) else 'building'
        if unit.get('state') in {'implemented', 'reviewing'}: return 'reviewing'
        if any(by_id.get(d, {}).get('state') != 'accepted' for d in unit.get('depends_on', [])): return 'waiting'
        return 'planned'
    rows = []
    for index, u in enumerate(units):
        label = tasks.get(u['id'], {'title': f"{ROLES.get(u.get('owner'), 'Trabajo')} · etapa {index+1}",
                                   'purpose': 'Preparando una explicación de esta tarea.', 'outcome': 'La entrega esperada todavía se está describiendo.'})
        rows.append({**label, 'id': u['id'], 'status': status(u), 'owner': ' · '.join(dict.fromkeys(ROLES.get(j.get('role'), 'Equipo') for j in state.get('jobs', []) if j.get('unit') == u['id'] and j.get('status') in ACTIVE)) or ROLES.get(u.get('owner'), 'Equipo'),
                     'dependencies': [tasks.get(d, {}).get('title', 'Otra etapa del proyecto') for d in u.get('depends_on', []) if by_id.get(d,{}).get('state') != 'accepted']})
    mapped = {u['id']: u for u in rows}
    capabilities = []
    for c in copy['capabilities'] if copy else []:
        states = [mapped[i]['status'] for i in c['units']]
        status_value = 'verified' if all(s == 'verified' for s in states) else next((s for s in ['building','reviewing','waiting'] if s in states), 'planned')
        capabilities.append({**c, 'status': status_value, 'verified': states.count('verified'), 'total': len(states)})
    return {'name': copy['name'] if copy else Path(state['request']['workspace']).name,
            'purpose': copy['purpose'] if copy else 'El equipo está preparando el proyecto y su plan de trabajo.',
            'communication': 'current' if copy else 'pending', 'communicated_at': record.get('generated_at'),
            'tasks': rows, 'capabilities': capabilities,
            'verified': sum(u['status']=='verified' for u in rows),
            'active': sum(u['status'] in {'building','reviewing'} for u in rows),
            'issues': sum(i.get('status')=='open' for i in state.get('issues', {}).values()),
            'published': False}
