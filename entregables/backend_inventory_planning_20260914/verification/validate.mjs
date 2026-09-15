import { PGlite } from '@electric-sql/pglite';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const db = new PGlite();
const checks = [];
const scripts = [
 'migrations/inventory/V20260914150001__normalize_product_site_replenishment.sql',
 'migrations/inventory/V20260914150002__explicit_planning_logistics.sql',
 'migrations/supply_planning/V20260914150003__forecast_planning_input_snapshot.sql',
];
const code = await Promise.all(scripts.map(p => readFile(resolve(root,p),'utf8')));
const id = n => `00000000-0000-0000-0000-${String(n).padStart(12,'0')}`;
async function test(name, fn) { await fn(); checks.push({name,status:'PASSED'}); }
async function rejected(sql, codes) {
 let failure;
 try { await db.exec(sql); } catch (e) { failure = e; }
 assert.ok(failure, 'Expected SQL failure');
 if(codes) assert.ok(codes.includes(failure.code), `Unexpected ${failure.code}: ${failure.message}`);
}
async function value(sql,key) { return (await db.query(sql)).rows[0][key]; }
const insert = (pair=21,days='15.2500',over='2.5000') => `INSERT INTO inventory.inv_product_site_replenishment
 (product_site_id,target_stock_days,overstock_days,minimum_order_quantity,preparation_days)
 VALUES('${id(pair)}',${days},${over},0,1.2500)`;

try {
 await db.exec(await readFile(resolve(here,'baseline_fixture.sql'),'utf8'));
 await test('reset refuses a database other than TEST', async()=>{
   await rejected(await readFile(resolve(root,'preparation/00_reset_test_replenishment.sql'),'utf8'),['P0001']);
   await db.exec('ROLLBACK');
   assert.equal(Number(await value('select count(*) as n from inventory.inv_product_site_replenishment','n')),1);
 });
 await test('migration refuses nonempty old table and transaction preserves data',async()=>{
   await rejected('BEGIN;'+code[0],['P0001']); await db.exec('ROLLBACK');
   assert.equal(Number(await value('select count(*) as n from inventory.inv_product_site_replenishment','n')),1);
 });
 // Synthetic local reset only; never calls TEST.
 await db.exec('DELETE FROM inventory.inv_product_site_replenishment');
 await test('all migrations execute transactionally',async()=>{
   for(const sql of code) await db.exec('BEGIN;'+sql+'COMMIT;');
 });
 await test('obsolete names are absent and no business data invented',async()=>{
   assert.equal(Number(await value("select count(*) as n from information_schema.columns where table_schema='inventory' and table_name='inv_product_site_replenishment' and column_name in ('target_coverage_days','safety_stock_days')",'n')),0);
   assert.equal(Number(await value('select count(*) as n from inventory.inv_product_site_replenishment','n')),0);
 });
 await test('maintenance requires explicit actor',()=>rejected(insert(),['P0001']));
 await db.exec("SELECT set_config('app.actor','local-test-actor',false)");
 await test('fractional days retained and legacy value does not override',async()=>{
   await db.exec(insert());
   const r=(await db.query('select * from inventory.inv_planning_parameters_v')).rows[0];
   assert.equal(Number(r.target_stock_days),15.25); assert.equal(Number(r.overstock_days),2.5);
   assert.equal(Number(r.preparation_days),1.25); assert.equal(Number(r.replenishment_row_version),1);
 });
 await test('both policy days mandatory, zero allowed',async()=>{
   await rejected(insert(22,'NULL'),['23502']); await rejected(insert(22,'0','NULL'),['23502']);
   await db.exec(insert(22,'0','0'));
 });
 await test('unique product/site parameter row',()=>rejected(insert(),['23505']));
 await test('unknown product/site rejected',()=>rejected(insert(999),['23503']));
 await test('negative days rejected',()=>rejected("UPDATE inventory.inv_product_site_replenishment SET target_stock_days=-1",['23514']));
 await test('NaN and infinities rejected',async()=>{
   for(const v of ['NaN','Infinity','-Infinity']) await rejected(`UPDATE inventory.inv_product_site_replenishment SET overstock_days='${v}'`,['23514','22003']);
 });
 await test('nonpositive multiples rejected, NULL remains optional',async()=>{
   await rejected('UPDATE inventory.inv_product_site_replenishment SET order_multiple=0',['23514']);
   await db.exec(`UPDATE inventory.inv_product_site_replenishment SET order_multiple=NULL WHERE product_site_id='${id(21)}'`);
 });
 await test('revision and optimistic update contract',async()=>{
   const rev=Number(await value(`SELECT row_version FROM inventory.inv_product_site_replenishment WHERE product_site_id='${id(21)}'`,'row_version'));
   const sql=`UPDATE inventory.inv_product_site_replenishment SET target_stock_days=16.5 WHERE product_site_id='${id(21)}' AND row_version=${rev} RETURNING row_version`;
   assert.equal((await db.query(sql)).rows.length,1); assert.equal((await db.query(sql)).rows.length,0);
 });
 await test('parameter identity cannot be reassigned',()=>rejected(`UPDATE inventory.inv_product_site_replenishment SET id='${id(998)}'`,['P0001']));
 await test('audit keeps old/new values and actor',async()=>{
   const r=(await db.query("select * from inventory.inv_planning_parameter_audit where operation='UPDATE' order by id desc limit 1")).rows[0];
   assert.equal(r.actor,'local-test-actor'); assert.equal(Number(r.new_value.target_stock_days),16.5);
   assert.equal(Number(r.old_value.target_stock_days),15.25);
   await rejected('DELETE FROM inventory.inv_planning_parameter_audit',['P0001']);
   await rejected('TRUNCATE inventory.inv_planning_parameter_audit',['P0001']);
 });
 await test('inactive replenishment omitted by view',async()=>{
   await db.exec(`UPDATE inventory.inv_product_site_replenishment SET active=false WHERE product_site_id='${id(22)}'`);
   assert.equal(Number(await value('SELECT count(*) AS n FROM inventory.inv_planning_parameters_v','n')),1);
 });
 await test('no automatic selection from duplicate principal logistics',async()=>{
   assert.equal(Number(await value('SELECT count(*) AS n FROM inventory.inv_logistic_variable WHERE principal','n')),3);
   assert.equal(Number(await value('SELECT count(*) AS n FROM inventory.inv_planning_logistics_v','n')),0);
 });
 await test('selection cannot reference another product',()=>rejected(`INSERT INTO inventory.inv_product_planning_logistics(product_id,logistic_variable_id) VALUES('${id(1)}','${id(33)}')`,['23503']));
 await test('explicit selection is unique and preserves fractional purchase factor',async()=>{
   await db.exec(`INSERT INTO inventory.inv_product_planning_logistics(product_id,logistic_variable_id) VALUES('${id(1)}','${id(31)}')`);
   const r=(await db.query('SELECT * FROM inventory.inv_planning_logistics_v')).rows[0];
   assert.equal(r.usable_for_forecast,true); assert.equal(Number(r.purchase_factor),1.5);
   await rejected(`INSERT INTO inventory.inv_product_planning_logistics(product_id,logistic_variable_id) VALUES('${id(1)}','${id(32)}')`,['23505']);
 });
 await test('deactivation of chosen variable is visible and not silently replaced',async()=>{
   await db.exec(`UPDATE inventory.inv_logistic_variable SET active=false WHERE id='${id(31)}'`);
   assert.equal(await value('select usable_for_forecast from inventory.inv_planning_logistics_v','usable_for_forecast'),false);
   await db.exec(`UPDATE inventory.inv_logistic_variable SET active=true WHERE id='${id(31)}'`);
 });
 await test('selected logistic variable cannot be deleted',()=>rejected(`DELETE FROM inventory.inv_logistic_variable WHERE id='${id(31)}'`,['23503']));
 await test('forecast snapshot immutable and survives parameter deletion',async()=>{
   await db.exec(`INSERT INTO supply_planning.spl_forecast_planning_input(result_id,replenishment_id,replenishment_row_version,target_stock_days,overstock_days,preparation_days,logistic_variable_id,logistics_selection_row_version,captured_at,input_snapshot)
     SELECT '${id(51)}',replenishment_id,replenishment_row_version,target_stock_days,overstock_days,preparation_days,'${id(31)}',1,now(),'{"contract_version":"inventory-planning-v1","purchase_factor":"1.5"}'::jsonb
     FROM inventory.inv_planning_parameters_v`);
   await rejected('UPDATE supply_planning.spl_forecast_planning_input SET overstock_days=0',['P0001']);
   await db.exec(`DELETE FROM inventory.inv_product_site_replenishment WHERE product_site_id='${id(21)}'`);
   assert.equal(Number(await value('SELECT target_stock_days FROM supply_planning.spl_forecast_planning_input','target_stock_days')),16.5);
   await rejected('DELETE FROM supply_planning.spl_supply_forecast_execution_execute_result',['23503']);
 });
 const result={status:'PASSED',captured_at:new Date().toISOString(),engine:await value('SELECT version() AS v','v'),
   target_engine:'PostgreSQL 14.24, not executed against TEST',database_writes_to_test:0,
   limitation:'PGlite local PostgreSQL; synthetic minimal baseline. Does not run Flyway CLI, Java/API or multi-session concurrency.',
   migration_sha256:Object.fromEntries(scripts.map((p,i)=>[p,createHash('sha256').update(code[i]).digest('hex')])),checks};
 await writeFile(resolve(here,'results.json'),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({status:result.status,engine:result.engine,checks:checks.length,database_writes_to_test:0}));
} finally { await db.close(); }
