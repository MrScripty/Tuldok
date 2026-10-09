'use strict';
const path=require('node:path'),{execFileSync}=require('node:child_process'),{qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
execFileSync(process.env.POINTCLOUD_CONSUMER_PYTHON||process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',
  [path.join(root,'tests/check_pointcloud_consumer.py'),'--output',qaDirectory(root,'pointcloud-consumer')],
  {cwd:root,stdio:'inherit',timeout:60000});
