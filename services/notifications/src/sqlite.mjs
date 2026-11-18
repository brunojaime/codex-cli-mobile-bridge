import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
export function openDatabase(path) {
 const connection=new DatabaseSync(path);
 connection.exec('PRAGMA busy_timeout=10000; PRAGMA journal_mode=WAL;');
 connection.exec(readFileSync(new URL('../migrations/001-push.sql',import.meta.url),'utf8'));
 connection.exec(readFileSync(new URL('../migrations/002-trigger-idempotency.sql',import.meta.url),'utf8'));
 const statement=(sql,values=[])=>({
  bind(...input){return statement(sql,input);},
  async run(){const result=connection.prepare(sql).run(...values);return {meta:{changes:Number(result.changes)}};},
  async all(){return {results:connection.prepare(sql).all(...values)};},
  sql,values
 });
 return {connection,prepare:statement,async batch(statements){
  connection.exec('BEGIN IMMEDIATE');
  try{const out=statements.map(s=>({meta:{changes:Number(connection.prepare(s.sql).run(...s.values).changes)}}));connection.exec('COMMIT');return out;}
  catch(e){connection.exec('ROLLBACK');throw e;}
 }};
}
