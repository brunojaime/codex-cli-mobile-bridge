import copy,json
import pytest
from backend.app.application.services.team_communication import validate,presentation,fingerprint

def fixture():
 s={'id':'a'*24,'request':{'workspace':'/project/Orders','objective':'Manage deliveries'},'units':[
 {'id':'a','owner':'generator','state':'ready','objective':'API contracts','depends_on':[]},
 {'id':'b','owner':'ux','state':'ready','objective':'Delivery screen','depends_on':['a']}], 'jobs':[], 'issues':{}}
 c={'name':'Entregas','purpose':'Organizar envíos','tasks':[{'id':i,'title':title,'purpose':'Preparar el recorrido','outcome':'Poder organizar pedidos'} for i,title in [('a','Pedidos'),('b','Seguimiento')]],'capabilities':[{'title':'Envíos','purpose':'Conocer el avance','units':['a','b']}]}
 return s,c

def test_narrative_cannot_set_execution_truth_or_omit_work(tmp_path):
 s,c=fixture();validate(c,s)
 for bad in [dict(c,status='completed'),dict(c,tasks=c['tasks'][:1])]:
  with pytest.raises(ValueError):validate(bad,s)
 root=tmp_path/'communication';root.mkdir();(root/(s['id']+'.json')).write_text(json.dumps({'fingerprint':fingerprint(s),'copy':c}))
 p=presentation(s,tmp_path);assert p['tasks'][1]['status']=='waiting';assert p['verified']==0 and not p['published']
 s['units'][0]['state']='accepted';p=presentation(s,tmp_path);assert p['verified']==1 and p['tasks'][1]['status']=='planned';assert p['communication']=='current'
 s['units'][1]['objective']='New scope';assert presentation(s,tmp_path)['communication']=='pending'

def test_reviewer_and_builder_have_distinct_states_and_generic_fallback(tmp_path):
 s,c=fixture();s['jobs']=[{'unit':'a','status':'running','role':'reviewer'}]
 p=presentation(s,tmp_path);assert p['tasks'][0]['status']=='reviewing';assert 'API' not in json.dumps(p)
 s['jobs'][0]['role']='generator';assert presentation(s,tmp_path)['tasks'][0]['status']=='building'
 for name in ['Booking','Warehouse']:
  s['request']['workspace']='/projects/'+name;assert presentation(s,tmp_path)['name']==name
