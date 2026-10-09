'use strict';
const path=require('node:path'),{execFileSync}=require('node:child_process'),{qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
execFileSync(process.env.MESH_CONSUMER_PYTHON||process.env.POINTCLOUD_CONSUMER_PYTHON||process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',
 [path.join(root,'tests/check_native_binary_mesh_consumer.py'),'--output',qaDirectory(root,'native-binary-mesh-consumer')],
 {cwd:root,stdio:'inherit',timeout:300000,env:{...process.env,OMP_NUM_THREADS:'1',MKL_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1'}});
