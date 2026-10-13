'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const context={window:{addEventListener(){}},$(){return {addEventListener(){}};},Map};
vm.createContext(context);
for(const file of ['pointclouds.js','volume-editor.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),context);
const pointRecord={id:'source',content_hash:'hash',pointcloud:{point_count:1,properties:[{dtype:'float',name:'x'},{dtype:'float',name:'y'},{dtype:'float',name:'z'}],bounds:{min:[0,0,0],max:[0,0,0]},manifest:{units:'m',coordinate_system:{frame:'native',handedness:'right',up_axis:'z'}}}};
const point={id:'source',content_hash:'hash',point_count:1,sample_count:1,properties:[{name:'x',dtype:'float'},{name:'y',dtype:'float'},{name:'z',dtype:'float'}],bounds:pointRecord.pointcloud.bounds,units:'m',coordinate_system:pointRecord.pointcloud.manifest.coordinate_system,points:[[0,0,0]]};
assert.equal(context.decodePointcloudInspection(point,pointRecord),point,'persisted and fresh property dictionaries may use different key order');
for(const mutate of [p=>p.id='other',p=>p.content_hash='other',p=>p.sample_count=0,p=>p.points=[[NaN,0,0]],p=>p.properties.reverse(),p=>p.bounds.max[0]=1]){
  const invalid=structuredClone(point);mutate(invalid);assert.throws(()=>context.decodePointcloudInspection(invalid,pointRecord),/Invalid point cloud/);
}
const volumeRecord={id:'volume',content_hash:'hash',volume:{shape:[2,2,3],manifest:{units:'mm'}}};
const slice={id:'volume',content_hash:'hash',axis:'z',index:1,row_axis:'y',column_axis:'x',units:'mm',physical_origin:[0,0,1],physical_row_step:[0,1,0],physical_column_step:[1,0,0],values:[[0,1,2],[3,4,255]]};
assert.equal(context.decodeVolumeSlice(slice,volumeRecord,'z',1),slice);
for(const mutate of [p=>p.index=0,p=>p.row_axis='x',p=>p.values[0][0]=256,p=>p.values.pop(),p=>p.values[0].pop(),p=>p.physical_origin[0]=Infinity,p=>p.content_hash='other']){
  const invalid=structuredClone(slice);mutate(invalid);assert.throws(()=>context.decodeVolumeSlice(invalid,volumeRecord,'z',1),/Invalid native volume/);
}
console.log('PASS spatial controller boundaries: persisted property key order, source identity, bounded point samples and native uint8 slice shape/coordinate fields');
