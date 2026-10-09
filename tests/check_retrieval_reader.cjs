'use strict';
const path=require('node:path'),{execFileSync}=require('node:child_process');
const {qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
// Output custody is checked before Python, scratch files, or consumer imports.
const output=qaDirectory(root,'retrieval-reader');
execFileSync(process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',
 [path.join(root,'tests/check_retrieval_reader.py'),'--output',output],
 {cwd:root,stdio:'inherit',timeout:90000,env:{...process.env,
  OMP_NUM_THREADS:'1',MKL_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1'}});
