'use strict';
const path=require('node:path'),{execFileSync}=require('node:child_process');
const {qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
const output=qaDirectory(root,'image-detection-reader');
execFileSync(process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',
 [path.join(root,'tests/check_image_detection_reader.py'),'--output',output],
 {stdio:'inherit',cwd:root,env:{...process.env,OMP_NUM_THREADS:'1',MKL_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1'},timeout:60000});
