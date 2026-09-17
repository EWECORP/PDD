import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
const require=createRequire(new URL('../backend_inventory_planning_20260914/verification/package.json',import.meta.url));
const {PGlite}=require('@electric-sql/pglite');
const db=new PGlite();
const migration=await readFile(new URL('./V20260917160001__product_classification_value_catalog.sql',import.meta.url),'utf8');
const checks=[];
async function fails(sql,code){try{await db.exec(sql);}catch(e){assert.equal(e.code,code);return;}throw Error('Expected failure');}
async function test(name,fn){await fn();checks.push(name);}
try{
 await db.exec(`CREATE SCHEMA inventory;
 CREATE TABLE inventory.inv_product(id uuid PRIMARY KEY);
 CREATE TABLE inventory.inv_product_classification_type(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),value varchar NOT NULL UNIQUE,created_at timestamp DEFAULT now());
 CREATE TABLE inventory.inv_product_classification(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),product_id uuid NOT NULL REFERENCES inventory.inv_product(id),classification_type_id uuid NOT NULL REFERENCES inventory.inv_product_classification_type(id),classification_value varchar NOT NULL,valid_from date,valid_to date,active boolean NOT NULL DEFAULT false,created_at timestamp DEFAULT now());
 INSERT INTO inventory.inv_product VALUES('00000000-0000-0000-0000-000000000001');
 INSERT INTO inventory.inv_product_classification_type(value) VALUES('Clasificación Compra'),('Clasificación Venta');
 INSERT INTO inventory.inv_product_classification(product_id,classification_type_id,classification_value) SELECT '00000000-0000-0000-0000-000000000001',id,'1-Sensibles' FROM inventory.inv_product_classification_type WHERE value='Clasificación Compra';`);
 await test('nonempty non-TEST database refused',async()=>{await fails('BEGIN;'+migration,'P0001');await db.exec('ROLLBACK');});
 await db.exec('DELETE FROM inventory.inv_product_classification');
 await test('empty database migrates transactionally',()=>db.exec('BEGIN;'+migration+'COMMIT;'));
 await test('seven values, two types preserved',async()=>{
  assert.equal((await db.query('SELECT * FROM inventory.inv_product_classification_value')).rows.length,7);
  assert.equal((await db.query('SELECT * FROM inventory.inv_product_classification_type')).rows.length,2);
 });
 const v=(await db.query("SELECT * FROM inventory.inv_product_classification_value WHERE code='1'")).rows[0];
 const other=(await db.query("SELECT id FROM inventory.inv_product_classification_type WHERE value='Clasificación Venta'")).rows[0].id;
 const insert=(type,from="CURRENT_DATE",to='NULL')=>`INSERT INTO inventory.inv_product_classification(product_id,classification_type_id,classification_value_id,valid_from,valid_to) VALUES('00000000-0000-0000-0000-000000000001','${type}','${v.id}',${from},${to})`;
 await test('valid assignment active by default',async()=>{await db.exec(insert(v.classification_type_id));assert.equal((await db.query('SELECT active FROM inventory.inv_product_classification')).rows[0].active,true);});
 await test('wrong type rejected by composite FK',()=>fails(insert(other),'23503'));
 await test('empty/reversed interval rejected',()=>fails(insert(v.classification_type_id,"CURRENT_DATE","CURRENT_DATE"),'23514'));
 await test('duplicate code within type rejected',()=>fails(`INSERT INTO inventory.inv_product_classification_value(classification_type_id,code,description) VALUES('${v.classification_type_id}','1','Duplicate')`,'23505'));
 await test('same code in different type allowed',()=>db.exec(`INSERT INTO inventory.inv_product_classification_value(classification_type_id,code,description) VALUES('${other}','1','Venta 1')`));
 await test('referenced value cannot be deleted',()=>fails(`DELETE FROM inventory.inv_product_classification_value WHERE id='${v.id}'`,'23503'));
 const result={status:'PASSED',engine:(await db.query('select version() as v')).rows[0].v,checks,migration_sha256:createHash('sha256').update(migration).digest('hex'),database_writes_to_test:0,limitations:'Local PGlite, not PostgreSQL 14/Flyway. TEST-only deletion not run; non-TEST guard tested. Temporal exclusivity is a service responsibility.'};
 await writeFile(new URL('./validation_results.json',import.meta.url),JSON.stringify(result,null,2));
 console.log(JSON.stringify({status:result.status,checks:checks.length,database_writes_to_test:0}));
}finally{await db.close();}
