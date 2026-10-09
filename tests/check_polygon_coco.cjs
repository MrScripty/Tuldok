'use strict';
const path=require('node:path'),{execFileSync}=require('node:child_process');
const {qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
execFileSync(process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',[path.join(root,'tests/check_polygon_coco.py'),'--output',qaDirectory(root,'polygon-coco-reader')],{cwd:root,stdio:'inherit',timeout:90000,env:{...process.env,OMP_NUM_THREADS:'1',MKL_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1'}});
