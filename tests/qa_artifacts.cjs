// QA outputs are disposable; authored inputs belong in tests/fixtures.
'use strict';
const fs=require('node:fs'),path=require('node:path');
const directories=new Map();
function qaRoot(root,override=process.env.TULDOK_QA_OUTPUT_ROOT){
  root=fs.realpathSync(path.resolve(root));
  const requested=path.resolve(override||path.join(root,'build','qa'));
  let parent=requested;
  while(!fs.existsSync(parent))parent=path.dirname(parent);
  const output=path.resolve(fs.realpathSync(parent),path.relative(parent,requested));
  const relative=path.relative(root,output);
  if(!relative||(relative!=='..'&&!relative.startsWith('..'+path.sep)&&!path.isAbsolute(relative)
      &&!['build','output'].includes(relative.split(path.sep)[0])))
    throw Error('QA output must be outside the source tree or inside ignored build/output folders.');
  return output;
}
function qaDirectory(root,suite,override){
  if(!/^[a-z0-9-]+$/.test(suite))throw Error('Invalid QA suite name.');
  const base=qaRoot(root,path.join(qaRoot(root,override),suite)),key=base;
  if(!directories.has(key)){
    fs.mkdirSync(base,{recursive:true});
    directories.set(key,fs.mkdtempSync(path.join(base,'run-')));
  }
  return directories.get(key);
}
const screenshotOptions=Object.freeze({format:'jpeg',quality:85,captureBeyondViewport:false});
module.exports={qaRoot,qaDirectory,screenshotOptions};
