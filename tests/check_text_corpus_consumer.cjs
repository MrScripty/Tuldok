// Isolated real Chapter 11 reader/trainer gate; no downloads or remote models.
'use strict';
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
execFileSync(process.env.TEXT_CORPUS_CONSUMER_PYTHON||process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',
  [path.join(root,'tests/check_text_corpus_consumer.py'),'--output',qaDirectory(root,'text-corpus-consumer')],
  {stdio:'inherit',cwd:root,env:{...process.env,OMP_NUM_THREADS:'1',MKL_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1'},timeout:180000});
