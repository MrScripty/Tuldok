// Existing runtime only. No installation, model or producer execution.
'use strict';
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
execFileSync(process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',
  [path.join(root,'tests/check_native_sequence_consumer.py'),'--output',qaDirectory(root,'native-sequence-consumer')],
  {stdio:'inherit',cwd:root,env:{...process.env,OMP_NUM_THREADS:'1',MKL_NUM_THREADS:'1'},timeout:60000});
