'use strict';
// Native schema controls, independent of recipe execution or transport.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const window={workspaceEscape:value=>String(value??'')};vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/workspace-service.js'),'utf8'),{window,structuredClone});
function editor(schema,value){
  const ui=window.WorkspaceTypedParameters({schema,value,prefix:'typed'});let html,nodes={},errors=[];
  const root={querySelector:selector=>nodes[selector.slice(1)]};
  function render(){html=ui.html('Configuration');nodes={};for(const match of html.matchAll(/<(input|select|button)\b([^>]*)>/g)){
    const attributes=match[2],id=attributes.match(/id="([^"]+)"/)?.[1];if(id)nodes[id]={value:attributes.match(/value="([^"]*)"/)?.[1]||'',checked:/\bchecked\b/.test(attributes),addEventListener(name,fn){this[name]=fn;}};
  }ui.bind(root,render,text=>errors.push(text));}
  render();return {ui,root,get html(){return html;},get nodes(){return nodes;},errors,read:()=>structuredClone(ui.read(root)),render};
}
const scalar={type:'integer',minimum:1,maximum:8},schema={type:'object',additionalProperties:false,required:['widths','enabled'],properties:{widths:{type:'array',items:scalar,minItems:1,maxItems:3},enabled:{type:'boolean'},name:{type:'string',minLength:1,maxLength:8},mode:{type:'integer',enum:[1,3]}}};
const f=editor(schema,{widths:[2,4],enabled:false});
f.nodes['typed-value-0'].value='5';f.nodes['typed-array-0-add'].click();assert.match(f.html,/value="5"/,'Adding an item preserves edits in earlier items');assert.throws(f.read,/valid/);f.nodes['typed-value-2'].value='7';f.nodes['typed-value-3'].checked=true;assert.deepEqual(f.read(),{widths:[5,4,7],enabled:true});
f.nodes['typed-array-0-remove-2'].click();assert.deepEqual(f.read(),{widths:[5,4],enabled:true});
const optional=Object.keys(f.nodes).find(id=>id.startsWith('typed-optional-'));f.nodes[optional].change({target:{checked:true}});f.nodes['typed-value-4'].value='named';assert.equal(f.read().name,'named');
f.nodes['typed-value-0'].value='Infinity';assert.throws(f.read,/valid/);f.nodes['typed-value-0'].value='2.5';assert.throws(f.read,/valid/);f.nodes['typed-value-0'].value='9';assert.throws(f.read,/valid/);f.nodes['typed-value-0'].value='1';assert.equal(f.read().widths[0],1);
const numericEnum=editor({type:'object',additionalProperties:false,required:['choice'],properties:{choice:{type:'integer',enum:[0,2]}}},{choice:0});numericEnum.nodes['typed-value-0'].value='1';assert.equal(numericEnum.read().choice,2,'Native enum index retains numeric type');
const closed=editor({type:'object',additionalProperties:false,properties:{}},{extra:1});assert.throws(closed.read,/undeclared/);assert.throws(()=>editor({type:'array',items:scalar,maxItems:65},[]),/bounded/);
let deep=scalar,value=1;for(let n=0;n<10;n++){deep={type:'array',maxItems:1,items:deep};value=[value];}assert.throws(()=>editor(deep,value),/depth|size/);
console.log('PASS native typed parameters: edited arrays preserve values, optional controls, numeric enums, finite/range/integer constraints, closed objects and bounded arrays/depth. No runtime or model execution.');
