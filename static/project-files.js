'use strict';
// One page owns this projection. The server owns project state and every edit.
(()=>{
  const $=id=>document.getElementById(id), base='/api/workspace/project-files';
  const actions=['new','open','save','close','query','get','import_text','annotate'];
  const tasks=['text_classification','text_entities','text_corpus'];
  // Generated from agent_api; freshness is checked by the client contract tests.
  const pins = /* PROJECT_FILES_CONTRACTS_START */ {
  "project_files.status": "1d0c4b64caaab8369d4addefd72e53cc8c7d0be4c07729fa04b358febe643b6a",
  "project_files.new": "672373f8ddc0b89fea15165798aab97cf4ac2cdf678a04d96839512cc8976b6f",
  "project_files.open": "fd4b9f97c03cd7050981cfafd1177bff8c86351bb603b8f7980aaa149d2b0368",
  "project_files.save": "38572e376db36f81582dc6419fded35ff9d7c9185f5af2cdaafd74c94790f90a",
  "project_files.close": "95d0099ec2a378a1bbb65676799dd3baae2f36b838301f7aa165b116fba5edf6",
  "project_files.query": "9a8b0d3a99adf5d7d53b62261dfac83e8b3ea44c10cb2f6c7a9c3d79422fef08",
  "project_files.get": "6b0f4e16a00aa119b86cbb5493be0bac945ff08a5e63773a8f2c2f9296658d5b",
  "project_files.import_text": "0f168320abb858892a2724b0b59862475bec653d1670ce754d61f2d82c912538",
  "project_files.annotate": "70feae2ad14c49c4ae95b5bb69b4a50fbf93191cde840544cf89b6cbe8dc5c58",
  "project_files.definitions": "3516fcf8764382780c7da699218a05ff1f811634656cc81722ef547f21159698",
  "project_files.data_query": "0a7585ed5c41ed28eee2505e95773741a7af82c74b5265b8ed4ebf2beb72e394",
  "project_files.data_get": "0d19505995cbd8c12e3938cd89cf05955a2a63488a220711d29dd24b27c0c8c8",
  "project_files.data_availability": "92332c04973a4fa45d47e384717152ebc4a9ca08e7eb487669688ccd2ed42cbb",
  "project_files.data_history": "b9e9e13389befe5f531d33d4d4d893649cb076f3eff98aa6ee85a4c46f03148a",
  "project_files.data_responses": "3e0c009244cad04fca4356cf3647bfd2b42cfc0d6a2ac31bb8de25cdb3c60ec8",
  "project_files.data_response_history": "1bd46a162efae7213ff7c8a7b77dfe843e952a629fd7c24af3b5298e04140224",
  "project_files.data_preferences": "35b9bff0cba8bf453d446a8b62a6d003cc49f6abb8a12b55bfb76a112c3f2067",
  "project_files.data_preference_history": "5ee7d60ce5e4aa09ea3496e9212b3404820d619cc2d47425faa94a3506d9ad07",
  "project_files.data_import_text": "c2db90c749154cb5489e13494d5a4404fdaf5a14895679fe2075fdfdc39e899d",
  "project_files.data_import_image": "e9f86ce62d29d267090c7955e0deb084f6ad6a936d1418baf5d807aa6d84ea3e",
  "project_files.data_import_audio": "51b511a068bed6ec024bd70bf08a48a23a94906362d54e0f3eb1223e325c237e",
  "project_files.data_import_mesh": "840d6e1d6ab326d144b63e275d60d304277b5d4867c9c170c6dde5e117b46107",
  "project_files.data_import_pointcloud": "c171b1342a5844fc1862947e20ae675395b8c3e24b44bff1179e0e8e6df70f53",
  "project_files.data_import_volume": "c6e509d797970afd7da9e2069c29736e290ada8e7034326b31e1cb707aa572e2",
  "project_files.data_import_sequence": "da8b91c9fd76d951fddc33acf6cca56287e0d7a29319b46032629b777af1f1ee",
  "project_files.source_register": "04390ea427cb9958f5a0a1118de5cf8f91434d12e9c241621cf11465d804c64e",
  "project_files.data_import_scientific": "a39ce46384bb2f0c3cdb9a6bbf881316ce166a26208fc41b4a88bb307af32d63",
  "project_files.data_annotate": "289270f5cb946765c5ced22fbbd18765bb55743145014c81cf54d7a6ba3025ea",
  "project_files.data_rights": "ead16cca68b03533daa81bf06148e1918ce40dbc823ee060bd9908581f788653",
  "project_files.data_source_save": "0d50c45d445b2ce1014a696c3bc95965f0b548ded939f4a650f985f34e1ce849",
  "project_files.data_source_delete": "457618e618cca92a71b668ffb9f68b0db87e51c417c2e5f41dcde76d71a23985",
  "project_files.data_response_save": "fa5b92afe529520fe8206d629bd88085a68f4f9b399cd40dd05fd3948d3592f0",
  "project_files.data_preference_save": "eacdaa8b32cac556f8a591c4ca3f1191d83182623bd425a5619e1c6920c17782",
  "project_files.data_preference_delete": "900538c7d8f74f04ed93387a864c8235b4162902345f6864b8d325527f63da5f",
  "project_files.selections": "fd9cc6a94144a349232e99aa1ad4890cb7cb4b023de8bf4e8249374aa29ec39d",
  "project_files.selection_get": "c99e320815d54b60d0ddb3179a0ee62fa5eca938ac71011813296ce93bb085b0",
  "project_files.selection_create": "87f60aeb83a497e7c6adab524f3ddc4776a6820497aa676f50ab3e1104b62ba2",
  "project_files.selection_rename": "7e3fe9853cc593e4c0464162b3c9137208500650a125a46704f1e38d49b6f5a1",
  "project_files.selection_delete": "cb021e6e1d7b4df1db1e4ca614067c3b26820737eca92dbc7168b3ff45b0894f",
  "project_files.searches": "061be81df13158c18c2a124419da07db9564b44c239c8ca80cbf65a7ad26c1bd",
  "project_files.search_create": "ae5c51158d849cda199cc007c42ea7a1cb62cd15a7ca8957bd32df813548e942",
  "project_files.search_rename": "78ca2aed2cd34c278ee1a9858dc76ebf8d39111de36bd48ada43f0407af5ff70",
  "project_files.search_delete": "518037dbe9464fd327df53f7801a3c1ba30bb822467c091a2bc684542a58495c",
  "project_files.release_preview": "0b6e2f0c2d7e3503fa29391fc20d27f058d0d3ad61e4547aee9845633ba6c5d8",
  "project_files.release_freeze": "93a1b5b3c6bf11f63c92571113ce536743e7fd07b0b77ae8aee6e909230245df",
  "project_files.models": "92e13621050d7f229a4785ed6845df2f191a9e037bcdf377fa7fb0ba796aebe3",
  "project_files.model_get": "95cc198ab6f084b596324f7251803ad4670a9f8e786e1a9639f1b9ed041798c3",
  "project_files.model_create": "34cf790fb2a3355ccab7c3a6c7174ced8dae861812d9479582fd8d5a9212745c",
  "project_files.model_save": "a90f8d985578191dee672824c9178559452f8b0dd759f74ed91337a96ca670e8",
  "project_files.graphs": "4892c990da89bc193d408537761e2e2db19694840ee652e64cba64a3bf57dbdb",
  "project_files.graph_get": "77eea46e63758f0ca172cd23595cf5a42fe9820dbc82f3aefb7f5b6c22dc23d9",
  "project_files.graph_create": "8fcb6d573b849ac03b5ee0ae192f274c11b9b5303451410ee46013f4cb0d83dc",
  "project_files.graph_save": "5a9745e4041cda6be46f63b83cb1f89d102d10c8810e41261a326cf0ef6821f4",
  "project_files.graph_create_external": "93d88731f66062c9d0ac15d38897e731e25e39df7f9b141e5f3277f2d07b4205",
  "project_files.graph_clone": "8f9b460530f0f136900734345fc338a1993ffdaddf5f4d90faf352c39f397514",
  "project_files.model_publish": "97c0ec706fd663d322764a2dd72bd920e7e7ac8defaee2d23624502ed239fc62",
  "project_files.recipes": "3217c2033f60242c661c6689d6f9f634ea9d3a9b188a9465edcdc0bea572bc6c",
  "project_files.recipe_get": "23837c51032b7c7ae6a365616f66cab9ae0d191108027291ad49898b2c421e2a",
  "project_files.recipe_create": "53a6760f03675d4d8a8d3a0ffd5b56689975667bbc136b1edf8a206307c18651",
  "project_files.recipe_save": "7fb9708aaba280ae437ee2554ecdaef3f724f3a7f4e55b49e54e1ef186691a7e",
  "project_files.recipe_prepare": "e91344f3032bf3e6abf50e5f5399252439498bce999c1f732322fd70a5eda1cf",
  "project_files.model_material": "46afde2b06e0e5b08565f12ec86d2d7ec43ef6b63d97c86c264fc9c2f451f20b",
  "project_files.recipe_material": "c384acbf2333d7dd360991d72c8e1e218dc3ad3291af76e09f76efe25ea69cc0",
  "project_files.runtime_material": "da48c927442878373434e93bb97fc65fc7056bd8e5a4b97e8a18627eb768cb07",
  "project_files.snapshot": "1eacdfeb7843bc432d62c6a94890dc07f618074faecb5e22589df9c9377e5030",
  "project_files.study": "b268a20042efe9c8bc260f74309688dc7bbbd60486d30a33621a68e1a92fa3d7",
  "project_files.trial": "79afa4bed6d0907f3d4116cc04cb784e94e5a24ab89725ec24f5d7bce70e869f",
  "project_files.run": "3cd94d46587596c36da4d1187b4648442cf6f216d2972daa496b7879e294ddec",
  "project_files.candidate": "c519ff04bc06d5e538d36b7f278862d8f282d0e7b97dd7f262444c384a50f854",
  "project_files.run_document_segment": "bd6599cb89b106ba0be4141fc5d38ad5e07b2c57c5b24e1fcf91802ba9ff9006",
  "project_files.source_references": "36a6d5b97efd63268d393b456e3bfec45cc696335acf652eff503b64a4ca0869",
  "project_files.publication_result": "10b4a5f3d4f37343322327024ddbedf5b6b69672c785e208ec48534d7b40c867",
  "project_files.package_state": "6f0369eafab3b8ed1db71ffb12e7d5a2bbcf400b46315d46ba1e2fb13e63baf7",
  "project_files.dependencies": "615e173c6e7cb811dc5e51ef6c368975b4dd06de14d6cf69fbd8c4bb01e3f9e4",
  "project_files.studies": "5c45e0938cef51c271d1e82b28e878bc831f5a9272773440e39022074e6e87b6",
  "project_files.runs": "cab46b11c5376ba641a717ceb1ce2bbe3693b7ac264e41192849f8522eb5d61d",
  "project_files.lineage": "750c173b42b113b6b82542fe4d82f8652cf07e1efe5cafde4c3e776d6afc3683",
  "project_files.policies": "629b61ae9bd9c65d04cd3e89fb50fb62dd455b9f75bcaf9db08b7890bb5516f5",
  "project_files.artifacts": "20a4031d189058721d09b8bf694ea9b1583eea410afd381f58fe6c70d0a0c339",
  "project_files.materials": "92a6a6a1750fed89aef9574ab6e82be2c6c6351bfa89fbfcb1f3866d4ea3cb13",
  "project_files.policy": "5bdb86600f2ec387fde721b22fdd0afa3ed47660126847c2908c1bb9de0421cb",
  "project_files.study_create": "8d2aac7c073a6a7b3ebb41227b5b466cf03606625404f93a59b325038a4ad7a1",
  "project_files.study_save": "5bf3fb814588fd7d9c35836e9d964a64481b3cc4169caf76cad6ce776ff0fe15",
  "project_files.trial_prepare": "e1f6973536fd4c356c4a92fc674d6766f7df0d8a113b8ee71bb05d0adc40b04f",
  "project_files.lineage_record": "16fd6cbd20bcd3743e4ac889dc6c398e714152f57d3c65cbd013f047c4267708",
  "project_files.candidate_select": "f043be6923760a208ca50d02a1ff4b60eadf09d48a034acdb18749806a537080",
  "project_files.evidence": "440d7dba608d633a4a42479018360ef2fa6609a47148e7edfdf5246f84c020ef",
  "project_files.retained_analysis": "05959a0e49a623318d6d70ded4f86df5df5d9bf29c411fcfcd1d9c0148b650cc",
  "project_files.retained_analysis_export": "fa5d97e094484da053a1374131040deefdac429ec8360d671f57b12353d69359",
  "project_files.artifact_status": "8dd0343f5f882c96cf023f8274734ca57175ae986e82b3bb1188cb5864784834",
  "project_files.artifact_resolve": "0df477e294b4e0729a707d7dfb6038414fc354e1ae50155eaacfa82b3a55f51f",
  "project_files.expose_holdout": "d69478ed54267ee1f1966f423f412a32f90b95a55997c6dc7d8348e3cdd78fd7",
  "project_files.producers": "65b2f4dff355c3bf5a023bf4f9dc116e302eda85ad90e6afaa2f21f0aa0667b5",
  "project_files.producer": "6187a9eb1e32cb3bcf13d283492b1ad909c32753aa5ed97fbc12a9708523d9e3"
} /* PROJECT_FILES_CONTRACTS_END */;
  // Generated fixed operation routes from agent_api; remote schemas are never executed.
  const m2Operations = /* PROJECT_FILES_ROUTES_START */ {
  "project_files.artifact_resolve": {
    "method": "POST",
    "path": "/api/workspace/project-files/artifacts/resolve",
    "mutation": true
  },
  "project_files.artifact_status": {
    "method": "POST",
    "path": "/api/workspace/project-files/artifacts/status",
    "mutation": false
  },
  "project_files.artifacts": {
    "method": "GET",
    "path": "/api/workspace/project-files/artifacts",
    "mutation": false
  },
  "project_files.candidate": {
    "method": "GET",
    "path": "/api/workspace/project-files/candidates/{candidate_id}",
    "mutation": false
  },
  "project_files.candidate_select": {
    "method": "POST",
    "path": "/api/workspace/project-files/studies/{study_id}/candidates",
    "mutation": true
  },
  "project_files.data_annotate": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/{record_id}",
    "mutation": true
  },
  "project_files.data_availability": {
    "method": "GET",
    "path": "/api/workspace/project-files/data/{record_id}/availability",
    "mutation": false
  },
  "project_files.data_get": {
    "method": "GET",
    "path": "/api/workspace/project-files/data/{record_id}",
    "mutation": false
  },
  "project_files.data_history": {
    "method": "GET",
    "path": "/api/workspace/project-files/data/{record_id}/history",
    "mutation": false
  },
  "project_files.data_import_audio": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-audio",
    "mutation": true
  },
  "project_files.data_import_image": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-image",
    "mutation": true
  },
  "project_files.data_import_mesh": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-mesh",
    "mutation": true
  },
  "project_files.data_import_pointcloud": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-pointcloud",
    "mutation": true
  },
  "project_files.data_import_scientific": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-scientific",
    "mutation": true
  },
  "project_files.data_import_sequence": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-sequence",
    "mutation": true
  },
  "project_files.data_import_text": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-text",
    "mutation": true
  },
  "project_files.data_import_volume": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/import-volume",
    "mutation": true
  },
  "project_files.data_preference_delete": {
    "method": "POST",
    "path": "/api/workspace/project-files/preferences/delete",
    "mutation": true
  },
  "project_files.data_preference_history": {
    "method": "GET",
    "path": "/api/workspace/project-files/data/{record_id}/preference-history",
    "mutation": false
  },
  "project_files.data_preference_save": {
    "method": "POST",
    "path": "/api/workspace/project-files/preferences",
    "mutation": true
  },
  "project_files.data_preferences": {
    "method": "GET",
    "path": "/api/workspace/project-files/data/{record_id}/preferences",
    "mutation": false
  },
  "project_files.data_query": {
    "method": "GET",
    "path": "/api/workspace/project-files/data",
    "mutation": false
  },
  "project_files.data_response_history": {
    "method": "GET",
    "path": "/api/workspace/project-files/data/{record_id}/response-history",
    "mutation": false
  },
  "project_files.data_response_save": {
    "method": "POST",
    "path": "/api/workspace/project-files/responses",
    "mutation": true
  },
  "project_files.data_responses": {
    "method": "GET",
    "path": "/api/workspace/project-files/data/{record_id}/responses",
    "mutation": false
  },
  "project_files.data_rights": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/{record_id}/rights",
    "mutation": true
  },
  "project_files.data_source_delete": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/{record_id}/source/delete",
    "mutation": true
  },
  "project_files.data_source_save": {
    "method": "POST",
    "path": "/api/workspace/project-files/data/{record_id}/source",
    "mutation": true
  },
  "project_files.definitions": {
    "method": "GET",
    "path": "/api/workspace/project-files/definitions",
    "mutation": false
  },
  "project_files.dependencies": {
    "method": "GET",
    "path": "/api/workspace/project-files/runs/{run_id}/dependencies",
    "mutation": false
  },
  "project_files.evidence": {
    "method": "POST",
    "path": "/api/workspace/project-files/runs/{run_id}/evidence",
    "mutation": false
  },
  "project_files.expose_holdout": {
    "method": "POST",
    "path": "/api/workspace/project-files/runs/{run_id}/disclose",
    "mutation": true
  },
  "project_files.graph_clone": {
    "method": "POST",
    "path": "/api/workspace/project-files/graphs/{graph_id}/clone",
    "mutation": true
  },
  "project_files.graph_create": {
    "method": "POST",
    "path": "/api/workspace/project-files/graphs",
    "mutation": true
  },
  "project_files.graph_create_external": {
    "method": "POST",
    "path": "/api/workspace/project-files/graphs/external",
    "mutation": true
  },
  "project_files.graph_get": {
    "method": "GET",
    "path": "/api/workspace/project-files/graphs/{graph_id}",
    "mutation": false
  },
  "project_files.graph_save": {
    "method": "POST",
    "path": "/api/workspace/project-files/graphs/{graph_id}",
    "mutation": true
  },
  "project_files.graphs": {
    "method": "GET",
    "path": "/api/workspace/project-files/graphs",
    "mutation": false
  },
  "project_files.lineage": {
    "method": "GET",
    "path": "/api/workspace/project-files/lineage",
    "mutation": false
  },
  "project_files.lineage_record": {
    "method": "POST",
    "path": "/api/workspace/project-files/lineage",
    "mutation": true
  },
  "project_files.materials": {
    "method": "GET",
    "path": "/api/workspace/project-files/materials",
    "mutation": false
  },
  "project_files.model_create": {
    "method": "POST",
    "path": "/api/workspace/project-files/models",
    "mutation": true
  },
  "project_files.model_get": {
    "method": "GET",
    "path": "/api/workspace/project-files/models/{model_id}",
    "mutation": false
  },
  "project_files.model_material": {
    "method": "POST",
    "path": "/api/workspace/project-files/materials/model",
    "mutation": false
  },
  "project_files.model_publish": {
    "method": "POST",
    "path": "/api/workspace/project-files/models/{model_id}/publish",
    "mutation": true
  },
  "project_files.model_save": {
    "method": "POST",
    "path": "/api/workspace/project-files/models/{model_id}",
    "mutation": true
  },
  "project_files.models": {
    "method": "GET",
    "path": "/api/workspace/project-files/models",
    "mutation": false
  },
  "project_files.package_state": {
    "method": "GET",
    "path": "/api/workspace/project-files/candidates/{candidate_id}/package-state",
    "mutation": false
  },
  "project_files.policies": {
    "method": "GET",
    "path": "/api/workspace/project-files/policies",
    "mutation": false
  },
  "project_files.policy": {
    "method": "POST",
    "path": "/api/workspace/project-files/policies/get",
    "mutation": false
  },
  "project_files.producer": {
    "method": "GET",
    "path": "/api/workspace/project-files/producers/{origin_catalog_id}/{producer_id}",
    "mutation": false
  },
  "project_files.producers": {
    "method": "GET",
    "path": "/api/workspace/project-files/producers",
    "mutation": false
  },
  "project_files.publication_result": {
    "method": "GET",
    "path": "/api/workspace/project-files/runs/{run_id}/publication-result",
    "mutation": false
  },
  "project_files.recipe_create": {
    "method": "POST",
    "path": "/api/workspace/project-files/recipes",
    "mutation": true
  },
  "project_files.recipe_get": {
    "method": "GET",
    "path": "/api/workspace/project-files/recipes/{recipe_id}",
    "mutation": false
  },
  "project_files.recipe_material": {
    "method": "POST",
    "path": "/api/workspace/project-files/materials/recipe",
    "mutation": false
  },
  "project_files.recipe_prepare": {
    "method": "POST",
    "path": "/api/workspace/project-files/recipes/{graph_id}/prepare",
    "mutation": true
  },
  "project_files.recipe_save": {
    "method": "POST",
    "path": "/api/workspace/project-files/recipes/{recipe_id}",
    "mutation": true
  },
  "project_files.recipes": {
    "method": "GET",
    "path": "/api/workspace/project-files/recipes",
    "mutation": false
  },
  "project_files.release_freeze": {
    "method": "POST",
    "path": "/api/workspace/project-files/releases/freeze",
    "mutation": true
  },
  "project_files.release_preview": {
    "method": "POST",
    "path": "/api/workspace/project-files/releases/preview",
    "mutation": false
  },
  "project_files.retained_analysis": {
    "method": "POST",
    "path": "/api/workspace/project-files/runs/{run_id}/analysis",
    "mutation": false
  },
  "project_files.retained_analysis_export": {
    "method": "POST",
    "path": "/api/workspace/project-files/runs/{run_id}/analysis/export",
    "mutation": false
  },
  "project_files.run": {
    "method": "GET",
    "path": "/api/workspace/project-files/runs/{run_id}",
    "mutation": false
  },
  "project_files.run_document_segment": {
    "method": "GET",
    "path": "/api/workspace/project-files/runs/{run_id}/document-segment",
    "mutation": false
  },
  "project_files.runs": {
    "method": "GET",
    "path": "/api/workspace/project-files/runs",
    "mutation": false
  },
  "project_files.runtime_material": {
    "method": "POST",
    "path": "/api/workspace/project-files/materials/runtime",
    "mutation": false
  },
  "project_files.search_create": {
    "method": "POST",
    "path": "/api/workspace/project-files/searches",
    "mutation": true
  },
  "project_files.search_delete": {
    "method": "POST",
    "path": "/api/workspace/project-files/searches/{search_id}/delete",
    "mutation": true
  },
  "project_files.search_rename": {
    "method": "POST",
    "path": "/api/workspace/project-files/searches/{search_id}",
    "mutation": true
  },
  "project_files.searches": {
    "method": "GET",
    "path": "/api/workspace/project-files/searches",
    "mutation": false
  },
  "project_files.selection_create": {
    "method": "POST",
    "path": "/api/workspace/project-files/selections",
    "mutation": true
  },
  "project_files.selection_delete": {
    "method": "POST",
    "path": "/api/workspace/project-files/selections/{selection_id}/delete",
    "mutation": true
  },
  "project_files.selection_get": {
    "method": "GET",
    "path": "/api/workspace/project-files/selections/{selection_id}",
    "mutation": false
  },
  "project_files.selection_rename": {
    "method": "POST",
    "path": "/api/workspace/project-files/selections/{selection_id}",
    "mutation": true
  },
  "project_files.selections": {
    "method": "GET",
    "path": "/api/workspace/project-files/selections",
    "mutation": false
  },
  "project_files.snapshot": {
    "method": "POST",
    "path": "/api/workspace/project-files/materials/snapshot",
    "mutation": false
  },
  "project_files.source_references": {
    "method": "GET",
    "path": "/api/workspace/project-files/sources/{project_id}/references",
    "mutation": false
  },
  "project_files.source_register": {
    "method": "POST",
    "path": "/api/workspace/project-files/sources/register",
    "mutation": true
  },
  "project_files.studies": {
    "method": "GET",
    "path": "/api/workspace/project-files/studies",
    "mutation": false
  },
  "project_files.study": {
    "method": "GET",
    "path": "/api/workspace/project-files/studies/{study_id}",
    "mutation": false
  },
  "project_files.study_create": {
    "method": "POST",
    "path": "/api/workspace/project-files/studies",
    "mutation": true
  },
  "project_files.study_save": {
    "method": "POST",
    "path": "/api/workspace/project-files/studies/{study_id}",
    "mutation": true
  },
  "project_files.trial": {
    "method": "GET",
    "path": "/api/workspace/project-files/trials/{trial_id}",
    "mutation": false
  },
  "project_files.trial_prepare": {
    "method": "POST",
    "path": "/api/workspace/project-files/studies/{study_id}/trials",
    "mutation": true
  }
} /* PROJECT_FILES_ROUTES_END */;
  let selectedContracts=new Set();
  let state=null, selected=null, history=[], summaries=[], nextRecord=null, nextHistory=null, epoch=0, busy=false, blocked=false;
  let importDirty=false, annotationDirty=false, m2Dirty=false, pending=null;
  let registeredSource=null,modelTemplates=[],templateBinding=null;
  let explored=null,exploreOffset=0,exploreTotal=0,historyOffset=0,historyTotal=0;
  const m2DirtyForms=new Set();
  const m2PagedActions=new Set(['data_query','data_history','data_responses','data_response_history',
    'data_preferences','data_preference_history','models','graphs','recipes','studies','runs',
    'lineage','policies','artifacts','materials','selections','searches','producers','source_references']);
  const m2HistoryActions=new Set(['data_history','data_response_history','data_preference_history']);
  const dirty=()=>importDirty||annotationDirty||m2Dirty;
  const checkpoint=()=>state?.project?.checkpoint??null;
  const exact=(value,keys)=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
  const str=(value,max,empty=false)=>typeof value==='string'&&Array.from(value).length<=max&&(empty||/\S/u.test(value));
  const id=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
  const sha=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
  const texts=(value,max,min=0,length=120)=>Array.isArray(value)&&value.length>=min&&value.length<=max&&new Set(value).size===value.length&&value.every(item=>str(item,length));
  const positive=value=>Number.isSafeInteger(value)&&value>0;
  function annotationOK(task,value,nullable=false){
    if(value===null)return nullable;
    if(task==='text_classification')return exact(value,['label'])&&str(value.label,80);
    if(task==='text_corpus')return exact(value,['note'])&&str(value.note,4000);
    return exact(value,['spans'])&&Array.isArray(value.spans)&&value.spans.length<=500&&value.spans.every(span=>exact(span,['label','start','end'])&&str(span.label,80)&&Number.isSafeInteger(span.start)&&span.start>=0&&positive(span.end)&&span.end>span.start);
  }
  function recordOK(value){
    const fields=['id','kind','name','text','groups','parents','provenance','task','annotation','review','revision','source_revision','created_at','updated_at'];
    return exact(value,fields)&&id(value.id)&&value.kind==='text'&&str(value.name,200)&&str(value.text,200000)&&texts(value.groups,30,1)&&texts(value.parents,30)&&exact(value.provenance,['method','rights','normalization'])&&value.provenance.method==='import'&&str(value.provenance.rights,1000)&&value.provenance.normalization==='NFC; LF newlines'&&tasks.includes(value.task)&&annotationOK(value.task,value.annotation,true)&&['draft','human_reviewed'].includes(value.review)&&positive(value.revision)&&value.source_revision===1&&str(value.created_at,80)&&str(value.updated_at,80);
  }
  function projectOK(value){return exact(value,['project_id','name','checkpoint'])&&id(value.project_id)&&str(value.name,200)&&sha(value.checkpoint);}
  function summaryOK(value){
    return exact(value,['id','kind','name','task','review','revision','source_revision','created_at','updated_at'])&&id(value.id)&&value.kind==='text'&&str(value.name,200)&&tasks.includes(value.task)&&['draft','human_reviewed'].includes(value.review)&&positive(value.revision)&&value.source_revision===1&&str(value.created_at,80)&&str(value.updated_at,80);
  }
  function receiptOK(value){
    const fields=['committed','selected','project_id','checkpoint','request_key'];
    return exact(value,value?.selected===false?[...fields,'root','directory']:fields)&&value.committed===true&&typeof value.selected==='boolean'&&id(value.project_id)&&sha(value.checkpoint)&&typeof value.request_key==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(value.request_key)&&(value.selected||(str(value.root,160)&&str(value.directory,512)));
  }
  function stateOK(value){
    const fields=['format','binding','state','roots','project','available_actions'];
    if(!exact(value,value?.state==='recovery_required'?[...fields,'recovery']:fields)||value.format!=='project_files_state_v1'||!id(value.binding)||!texts(value.roots,100,0,160)||!Array.isArray(value.available_actions)||value.available_actions.length>8||new Set(value.available_actions).size!==value.available_actions.length||!value.available_actions.every(action=>actions.includes(action)))return false;
    if(value.state==='no_project_open')return value.project===null;
    if(!projectOK(value.project))return false;
    if(value.state==='open')return true;
    const recovery=value.recovery;
    return value.state==='recovery_required'&&exact(recovery,['action','root','directory','reason','request_key'])&&recovery.action==='open'&&str(recovery.root,160)&&str(recovery.directory,512)&&['unknown_publication','projection_unavailable'].includes(recovery.reason)&&(recovery.request_key===null||typeof recovery.request_key==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(recovery.request_key))&&value.available_actions.length===1&&value.available_actions[0]==='open';
  }
  function boundOK(value,kind){
    const fields=kind==='query'?['binding','project_id','checkpoint','items','next_after_id']:['binding','project_id','checkpoint','record','history','next_history_before_revision'];
    if(!exact(value,fields)||!id(value.binding)||!id(value.project_id)||!sha(value.checkpoint))return false;
    if(kind==='query')return Array.isArray(value.items)&&value.items.length<=100&&value.items.every(summaryOK)&&(value.next_after_id===null||id(value.next_after_id)&&value.items.at(-1)?.id===value.next_after_id)&&value.items.every((item,index)=>index===0||item.id>value.items[index-1].id);
    return recordOK(value.record)&&Array.isArray(value.history)&&value.history.length<=4&&value.history.every(recordOK)&&value.history.every((item,index)=>item.id===value.record.id&&item.revision<=value.record.revision&&(index===0||item.revision<value.history[index-1].revision))&&(value.next_history_before_revision===null||positive(value.next_history_before_revision)&&value.history.at(-1)?.revision===value.next_history_before_revision);
  }
  function message(value){$('project-files-status').textContent=value;}
  function error(value){
    const node=$('project-files-error');node.textContent=value;node.hidden=false;node.focus();
  }
  function clearError(){$('project-files-error').hidden=true;$('project-files-error').textContent='';}
  function controls(){
    const open=state?.state==='open', allowed=action=>!busy&&!blocked&&selectedContracts.has('project_files.'+action)&&state?.available_actions.includes(action);
    for(const action of ['new','open','save','close'])$('project-files-'+action).disabled=!allowed(action);
    $('project-files-refresh').disabled=busy;
    $('project-files-root').disabled=busy||state?.state==='recovery_required';
    $('project-files-directory').disabled=busy||state?.state==='recovery_required';
    $('project-files-name').disabled=busy||state?.state==='recovery_required';
    $('text-import-fields').disabled=!open||!allowed('import_text');
    $('annotation-fields').disabled=!selected||!allowed('annotate');
    $('import-text').disabled=!allowed('import_text');
    $('annotation-save').disabled=!selected||!allowed('annotate');
    $('project-files-discard').disabled=busy||!dirty();
    $('records-more').hidden=nextRecord===null;$('records-more').disabled=!allowed('query');
    $('record-history-more').hidden=nextHistory===null;$('record-history-more').disabled=!selected||!allowed('get');
    $('project-files-open').textContent=state?.state==='recovery_required'?'Reopen to reconcile':'Open project';
    for(const button of $('records-list').querySelectorAll('button'))button.disabled=busy||blocked;
    $('project-files-dirty').textContent=dirty()?'This tab has unsent or unacknowledged edits. After an error, inspect saved state before retrying; explicitly discard these edits before closing. Unsent annotations must be resolved before selecting a different record.':'No unsubmitted edits.';
    m2Controls();
    if(window.TuldokAuth&&!window.TuldokAuth.canReview())$('record-review').value='draft';
  }
  function showState(){
    const root=$('project-files-root'), previous=root.value;root.replaceChildren();
    for(const alias of state.roots){const option=document.createElement('option');option.value=alias;option.textContent=alias;root.append(option);}
    if(state.roots.includes(previous))root.value=previous;
    const recovery=state.state==='recovery_required';
    $('project-files-summary').textContent=state.project?`${state.project.name} · ${state.project.project_id} · ${recovery?'last acknowledged':'saved'} checkpoint ${state.project.checkpoint}${recovery?' · Reopen this project to reconcile its saved state.':''}`:'No project open.';
    if(recovery){root.value=state.recovery.root;$('project-files-directory').value=state.recovery.directory;}
    controls();
  }
  function annotationHelp(){
    const task=$('annotation-task').value;
    $('annotation-label').textContent=task==='text_classification'?'Class label':task==='text_corpus'?'Corpus note':'Entity spans (JSON)';
    $('annotation-help').textContent=task==='text_classification'?'Enter one classification label, up to 80 characters.':task==='text_corpus'?'Enter a human-authored corpus note, up to 4,000 characters.':'Enter {"spans":[{"label":"person","start":0,"end":4}]}. Offsets count Unicode code points; an empty spans array records a negative.';
    $('annotation-value').maxLength=task==='text_classification'?80:task==='text_corpus'?4000:200000;
  }
  function showRecord(focus=false){
    $('record-heading').textContent=selected?selected.name:'Select a text record';
    $('record-summary').textContent=selected?`Revision ${selected.revision} · ${selected.review} · source revision ${selected.source_revision}`:'';
    $('record-text').value=selected?.text??'';
    $('annotation-task').value=selected?.task??'text_classification';
    const value=selected?.annotation;
    $('annotation-value').value=value?(selected.task==='text_entities'?JSON.stringify(value,null,2):value.label??value.note):'';
    $('annotation-groups').value=selected?.groups.join(', ')??'';
    $('record-review').value=selected?.review??'draft';
    annotationHelp();
    showHistory();controls();if(focus)$('record-heading').focus();
  }
  function showHistory(){
    const list=$('record-history');list.replaceChildren();
    for(const snapshot of history){const item=document.createElement('li'),title=document.createElement('p'),body=document.createElement('pre');title.textContent=`Revision ${snapshot.revision} · ${snapshot.review} · ${snapshot.task}`;body.textContent=JSON.stringify(snapshot.annotation,null,2);item.append(title,body);list.append(item);}
    controls();
  }
  function showRecords(items){
    const list=$('records-list');list.replaceChildren();
    if(!items.length){const item=document.createElement('li');item.textContent='No text records yet.';list.append(item);}
    for(const record of items){const item=document.createElement('li'),button=document.createElement('button');button.type='button';button.dataset.recordId=record.id;button.textContent=`${record.name} · ${record.review} · revision ${record.revision}`;button.setAttribute('aria-current',String(record.id===selected?.id));button.onclick=()=>select(record.id);item.append(button);list.append(item);}
    controls();
  }
  function needClean(){if(!dirty())return true;error('This tab has unsent or unacknowledged edits. Inspect saved state after an error, then submit or choose “Discard unsubmitted edits” before this action.');return false;}
  async function discover(ticket){
    let response,value;
    try{response=await window.TuldokAuth.fetch('/api/agent/capabilities',{cache:'no-store'});value=await response.json();}
    catch(_){const failure=Error('Project contracts unavailable. Refresh status before continuing.');failure.code='transport';throw failure;}
    if(ticket!==epoch)return false;
    if(!response.ok){const failure=Error(value?.error??'Project contracts unavailable. Sign in and refresh status.');failure.status=response.status;throw failure;}
    if(!exact(value,['format','envelope_version','catalog_id','operations','limits'])||value.format!=='agent_capabilities_v1'||value.envelope_version!==1||!id(value.catalog_id)||!Array.isArray(value.operations)||value.operations.length>256||JSON.stringify(value).length>1048576||!exact(value.limits,['request_bytes','response_bytes','max_operations'])||value.limits.request_bytes!==1048576||value.limits.response_bytes!==16777216||value.limits.max_operations!==256)throw Error('Unsupported project capability envelope.');
    const identity=window.TuldokAuth.identity?.();
    if(identity?.catalog_id&&identity.catalog_id!==value.catalog_id)throw Error('Project capability catalog differs from the current session.');
    const names=new Set(),chosen=new Set();
    for(const operation of value.operations){
      if(!exact(operation,['id','contracts','availability'])||typeof operation.id!=='string'||!/^[a-z][a-z0-9_.]{0,79}$/.test(operation.id)||names.has(operation.id)||!['available','unavailable','unsupported'].includes(operation.availability)||!Array.isArray(operation.contracts)||!operation.contracts.length||operation.contracts.length>4)throw Error('Unsupported operation capability.');
      names.add(operation.id);const versions=new Set();
      for(const contract of operation.contracts){
        if(!exact(contract,['version','sha256','input_schema','output_schema','scopes','authority','effects','retry','bounds'])||!positive(contract.version)||versions.has(contract.version)||!sha(contract.sha256)||!contract.input_schema||typeof contract.input_schema!=='object'||Array.isArray(contract.input_schema)||!contract.output_schema||typeof contract.output_schema!=='object'||Array.isArray(contract.output_schema)||!texts(contract.scopes,16,0,40)||!['agent','owner'].includes(contract.authority)||!['read','mutation'].includes(contract.effects)||!['read','cas','receipt','never'].includes(contract.retry)||!exact(contract.bounds,['request_bytes','response_bytes','inline_decoded_bytes','json_depth'])||!Object.values(contract.bounds).every(positive))throw Error('Unsupported operation contract.');
        versions.add(contract.version);
        // Remote schemas are opaque discovery data; only installed local pins
        // select behavior. Every request lets the owner verify this exact pin.
        if(operation.availability==='available'&&contract.version===1&&Object.hasOwn(pins,operation.id)&&contract.sha256===pins[operation.id])chosen.add(operation.id);
      }
    }
    selectedContracts=chosen;
    if(!chosen.has('project_files.status')){const failure=Error('No compatible project status contract is available.');failure.code='contract_mismatch';throw failure;}
    return true;
  }
  async function request(path,{body,kind='state',ticket=epoch,read=false,recordId}={}){
    const binding=state?.binding, expected=checkpoint(), project=state?.project?.project_id;
    const action=path===''?'status':path.startsWith('/records?')?'query':path.startsWith('/records/')?(body===undefined?'get':'annotate'):path.slice(1).replaceAll('-','_');
    const operation='project_files.'+action;
    if(!selectedContracts.has(operation)){const failure=Error('No compatible contract is available for '+action+'. Refresh project status.');failure.code='contract_mismatch';throw failure;}
    let response,value;
    try{
      response=await window.TuldokAuth.fetch(base+path,{method:body===undefined?'GET':'POST',headers:{'Tuldok-Operation-Contract':operation+'/1/'+pins[operation],...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
      value=await response.json();
    }catch(_){const failure=Error(body===undefined?'Project response unavailable. Refresh status to recover.':'Acknowledgement unavailable; the edit may already be saved. Keep your edits and refresh status before retrying.');failure.code='transport';throw failure;}
    if(ticket!==epoch){message('A superseded project response was ignored. The current view is unchanged.');return null;}
    if(!response.ok){const fields=['error',...(Object.hasOwn(value??{},'code')?['code']:[]),...(Object.hasOwn(value??{},'receipt')?['receipt']:[])];const valid=exact(value,fields)&&str(value.error,1000)&&(!Object.hasOwn(value,'code')||str(value.code,120))&&(!Object.hasOwn(value,'receipt')||receiptOK(value.receipt));const failure=Error(valid?`${value.code??'error'}: ${value.error}`:'Invalid project error response. Refresh status.');failure.code=valid?(value.code??'http_error'):'transport';failure.status=response.status;if(valid&&value.receipt)failure.receipt=value.receipt;throw failure;}
    if(!(kind==='state'?stateOK(value):boundOK(value,kind))){const failure=Error('Unsupported project response. The current state is unknown; refresh status before continuing.');failure.code='transport';throw failure;}
    if(kind!=='state'&&(value.binding!==binding||value.project_id!==project||(read&&value.checkpoint!==expected)||(recordId&&value.record?.id!==recordId))){const failure=Error('stale: Response belongs to a different project or checkpoint. Your unsubmitted edits remain here. Refresh status.');failure.code='stale';throw failure;}
    return value;
  }
  async function run(work,{clean=false}={}){
    if(busy)return;if(clean&&!needClean())return;
    const ticket=++epoch;busy=true;clearError();controls();
    let nextFocus=null;
    try{nextFocus=await work(ticket);}catch(failure){
      if(ticket===epoch){
        if(failure.status===409||failure.status>=500||['stale','conflict','binding_mismatch','transport','projection_unavailable','stale_binding','stale_checkpoint','too_large'].includes(failure.code))blocked=true;
        if(failure.receipt){const receipt=failure.receipt;$('project-files-receipt').hidden=false;$('project-files-receipt').textContent=`Saved to project ${receipt.project_id} at checkpoint ${receipt.checkpoint}; request ${receipt.request_key}. ${receipt.selected?'Refresh status and reopen to restore the local view.':'The project was created but is not selected. Refresh status, then Open its directory.'}`;if(!receipt.selected){$('project-files-root').value=receipt.root;$('project-files-directory').value=receipt.directory;}}
        error(failure.message);
      }
    }finally{if(ticket===epoch){busy=false;controls();if(nextFocus)nextFocus.focus();}}
  }
  async function query(ticket,append=false){
    if(state?.state!=='open'){summaries=[];nextRecord=null;showRecords([]);return;}
    const cursor=append?nextRecord:null,parameters={binding:state.binding,checkpoint:checkpoint()};
    if(cursor!==null)parameters.after_id=cursor;
    const result=await request('/records?'+new URLSearchParams(parameters),{kind:'query',ticket,read:true});
    if(result){if(cursor!==null&&result.items.some(item=>item.id<=cursor))throw Error('Invalid record-page continuation. Refresh status.');summaries=append?[...summaries,...result.items]:result.items;nextRecord=result.next_after_id;showRecords(summaries);}
  }
  function olderHistory(){return run(async ticket=>{
    if(!selected||nextHistory===null)return;
    const before=nextHistory;
    const result=await request('/records/'+selected.id+'?'+new URLSearchParams({binding:state.binding,checkpoint:checkpoint(),before_revision:before}),{kind:'record',ticket,read:true,recordId:selected.id});
    if(!result)return;
    if(result.record.revision!==selected.revision||result.history.some(item=>item.revision>=before))throw Error('Invalid history-page continuation. Refresh status.');
    history=[...history,...result.history];nextHistory=result.next_history_before_revision;showHistory();message('Older saved annotation history loaded.');return nextHistory===null?$('record-history-title'):$('record-history-more');
  });}
  function refresh(){return run(async ticket=>{
    if(!await discover(ticket))return;
    const value=await request('',{ticket});if(!value)return;
    const changed=state?.binding!==value.binding||checkpoint()!==value.project?.checkpoint;
    state=value;blocked=false;
    if(changed){clearExploration();selected=null;history=[];nextHistory=null;if(!annotationDirty)showRecord();else{$('record-heading').textContent='Unsubmitted annotation from a prior checkpoint';$('record-summary').textContent='Project changed. Your unsubmitted annotation remains below; discard it before selecting a saved record.';$('record-text').value='';}}
    showState();await query(ticket);message(dirty()?'Project status refreshed. Unsubmitted edits remain in this tab.':'Project status refreshed.');
  });}
  function select(recordId){if(annotationDirty){error('The annotation editor has unsent or unacknowledged edits. Submit or explicitly discard that annotation before selecting a saved record.');return;}return run(async ticket=>{
    const result=await request('/records/'+recordId+'?'+new URLSearchParams({binding:state.binding,checkpoint:checkpoint()}),{kind:'record',ticket,read:true,recordId});
    if(!result)return;selected=result.record;history=result.history;nextHistory=result.next_history_before_revision;annotationDirty=false;showRecord(true);await query(ticket);message('Saved text and annotation history loaded.');
  });}
  function key(){return crypto.randomUUID().replaceAll('-','');}
  function mutationBody(path,fields){
    const body={binding:state.binding,expected_checkpoint:checkpoint(),...fields};
    const signature=JSON.stringify({path,body});
    if(!pending||pending.signature!==signature)pending={signature,key:key()};
    return {...body,request_key:pending.key};
  }
  function lifecycle(action){const recovering=action==='open'&&state?.state==='recovery_required';return run(async ticket=>{
    const fields={};
    if(['new','open'].includes(action)){
      if(!$('project-files-root').value||!$('project-files-directory').value.trim())throw Error('Choose a local root and relative project directory.');
      fields.root=$('project-files-root').value;fields.directory=$('project-files-directory').value;
      if(action==='new'){if(!$('project-files-name').value.trim())throw Error('Enter a name for the new project.');fields.name=$('project-files-name').value;}
    }
    const value=await request('/'+action,{ticket,body:mutationBody('/'+action,fields)});if(!value)return;
    state=value;pending=null;if(action!=='save'){clearExploration();selected=null;history=[];nextHistory=null;}showState();if(action!=='save'&&!annotationDirty)showRecord();else if(recovering&&annotationDirty){$('record-heading').textContent='Preserved unsubmitted annotation';$('record-text').value='';}await query(ticket);message(action==='save'?'Project checkpoint is saved.':action==='close'?'Project closed.':`Project ${action==='new'?'created':'opened'}.`);
    return action==='save'?$('project-files-save'):(state.state==='open'?$('text-name'):$('project-files-directory'));
  },{clean:!recovering});}
  function groups(value){const result=value.split(',').map(item=>item.trim()).filter(Boolean);if(!texts(result,30,1))throw Error('Supply 1–30 distinct protected group IDs, each up to 120 characters.');return result;}
  async function acceptRecord(value,ticket){
    state={...state,project:{...state.project,checkpoint:value.checkpoint}};selected=value.record;history=value.history;nextHistory=value.next_history_before_revision;pending=null;annotationDirty=false;showState();showRecord(true);await query(ticket);
  }
  $('text-import-form').onsubmit=event=>{
    event.preventDefault();if(annotationDirty){error('Submit or discard the current annotation before creating another text record.');return;}
    run(async ticket=>{
      const asset={name:$('text-name').value,text:$('text-content').value,groups:groups($('text-groups').value),rights:$('text-rights').value};
      if(!str(asset.name,200)||!str(asset.text,200000)||!str(asset.rights,1000))throw Error('Enter a name, text and rights note within the displayed limits.');
      const value=await request('/import-text',{kind:'record',ticket,body:mutationBody('/import-text',{asset})});if(!value)return;
      importDirty=false;$('text-name').value='';$('text-content').value='';await acceptRecord(value,ticket);message('Text submitted and saved to the project.');
    });
  };
  $('annotation-form').onsubmit=event=>{
    event.preventDefault();run(async ticket=>{
      if(!selected)throw Error('Select a saved text record first.');
      const task=$('annotation-task').value,raw=$('annotation-value').value;
      let annotation;if(task==='text_entities'){try{annotation=JSON.parse(raw);}catch(_){throw Error('Entity spans must be valid JSON.');}}else annotation=task==='text_corpus'?{note:raw}:{label:raw};
      if(!annotationOK(task,annotation))throw Error('The annotation does not match this task. Follow the instructions above the editor.');
      const body={revision:selected.revision,source_revision:selected.source_revision,task,annotation,groups:groups($('annotation-groups').value),review:$('record-review').value};
      const value=await request('/records/'+selected.id,{kind:'record',ticket,recordId:selected.id,body:mutationBody('/records/'+selected.id,{annotation:body})});if(!value)return;
      await acceptRecord(value,ticket);message('Annotation submitted and saved to the project.');
    });
  };
  function projectValue(value,depth=0){
    const box=document.createElement('div');
    if(value===null||typeof value!=='object'){box.textContent=value===null?'Not recorded':String(value);return box;}
    if(depth>5){box.textContent='Further saved details available through the project API.';return box;}
    const entries=Array.isArray(value)?value.map((item,index)=>[String(index+1),item]):Object.entries(value);
    const list=document.createElement('dl');
    for(const [name,item] of entries){
      const term=document.createElement('dt'),definition=document.createElement('dd');term.textContent=name.replaceAll('_',' ');
      if(item!==null&&typeof item==='object'){
        const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=Array.isArray(item)?`${item.length} saved items`:'Saved details';details.append(summary,projectValue(item,depth+1));definition.append(details);
      }else definition.textContent=item===null?'Not recorded':String(item);
      list.append(term,definition);
    }
    box.append(list);return box;
  }
  const m2Allowed=action=>!busy&&!blocked&&state?.state==='open'&&selectedContracts.has('project_files.'+action);
  function m2Controls(){
    const action=$('project-explore-kind').value;
    $('project-explore-load').disabled=!m2Allowed(action);
    $('project-explore-more').disabled=!m2Allowed(action);
    for(const [field,operation] of [['project-source-fields','data_import_'+$('project-source-kind').value],['project-search-fields','search_create'],['project-selection-fields','selection_create'],['project-rights-fields','data_rights'],['project-data-note-fields','data_annotate']])$(field).disabled=!m2Allowed(operation)||(['project-selection-fields','project-rights-fields','project-data-note-fields'].includes(field)&&(!explored||explored.checkpoint!==checkpoint()));
    $('project-definitions-load').disabled=!m2Allowed('definitions');
    $('project-model-create-fields').disabled=!modelTemplates.length||templateBinding!==state?.binding||!m2Allowed('model_create');
    $('project-model-publish').disabled=!explored||explored.category!=='models'||explored.checkpoint!==checkpoint()||!m2Allowed('model_publish');
    $('project-study-create-fields').disabled=!m2Allowed('study_create');
    $('project-register-fields').disabled=!m2Allowed('source_register');
    $('project-source-references-more').disabled=!m2Allowed('source_references');
    $('project-scientific-fields').disabled=!registeredSource||registeredSource.binding!==state?.binding||!m2Allowed('data_import_scientific');
    $('project-artifact-status').disabled=!explored||explored.category!=='artifacts'||!m2Allowed('artifact_status');
    $('project-artifact-resolve-fields').disabled=!explored||explored.category!=='artifacts'||!m2Allowed('artifact_resolve');
    $('project-metadata-fields').disabled=!explored||explored.checkpoint!==checkpoint()||!m2Allowed(explored.saveAction);
    for(const name of ['project-detail-history','project-detail-availability','project-run-evidence','project-run-document','project-run-disclose','project-detail-history-more'])$(name).disabled=busy||blocked||state?.state!=='open';
    for(const button of $('project-explore-list').querySelectorAll('button'))button.disabled=busy||blocked;
  }
  function clearExploration(){
    explored=null;exploreOffset=0;exploreTotal=0;historyOffset=0;historyTotal=0;
    $('project-explore-list').replaceChildren();$('project-detail-facts').replaceChildren();$('project-detail-history-list').replaceChildren();
    $('project-detail-title').textContent='Choose a saved record';$('project-explore-summary').textContent='';
    for(const name of ['project-metadata-form','project-data-note-form','project-rights-form','project-selection-form','project-detail-history','project-detail-history-more','project-detail-availability','project-run-evidence','project-run-document','project-run-disclose','project-disclosure-label','project-model-publish','project-artifact-status','project-artifact-resolve-form','project-explore-more'])if(!m2DirtyForms.has(name))$(name).hidden=true;
    if(m2Dirty)$('project-detail-title').textContent='Preserved unsubmitted metadata; discard it before selecting a saved record.';
  }
  async function m2Request(action,arguments_,ticket){
    const operation='project_files.'+action,definition=m2Operations[operation];
    if(!definition||!selectedContracts.has(operation))throw Error('This operation is unavailable for the selected project.');
    const binding=state.binding,cp=checkpoint(),project=state.project.project_id;
    let values={binding,[definition.mutation?'expected_checkpoint':'checkpoint']:cp,...arguments_};
    let path=definition.path;
    for(const [name,value] of Object.entries(values))path=path.replace('{'+name+'}',encodeURIComponent(value));
    const remaining=Object.fromEntries(Object.entries(values).filter(([name])=>!definition.path.includes('{'+name+'}')));
    const options={method:definition.method,cache:'no-store',headers:{'Tuldok-Operation-Contract':operation+'/1/'+pins[operation]}};
    if(definition.method==='GET')path+='?'+new URLSearchParams(remaining);
    else{
      if(definition.mutation){const prepared=mutationBody(path,arguments_);values={...values,request_key:prepared.request_key};remaining.request_key=prepared.request_key;}
      options.headers['Content-Type']='application/json';options.body=JSON.stringify(remaining);
      if(new TextEncoder().encode(options.body).length>1048576)throw Error('This source exceeds the synchronous import limit. Choose a smaller source.');
    }
    let response,value;
    try{response=await window.TuldokAuth.fetch(path,options);value=await response.json();}
    catch(_){const failure=Error(definition.mutation?'Acknowledgement unavailable; this change may already be saved. Keep your edits and refresh project status.':'Saved history is unavailable. Refresh project status.');failure.code='transport';throw failure;}
    if(ticket!==epoch)return null;
    if(!response.ok){
      const failure=Error(str(value?.error,1000)?value.error:'Unsupported project error response.');failure.code=value?.code??'transport';failure.status=response.status;
      if(value?.receipt){if(!receiptOK(value.receipt)||value.receipt.request_key!==values.request_key||value.receipt.project_id!==project||!value.receipt.selected){const invalid=Error('Project receipt belongs to a different request.');invalid.code='transport';throw invalid;}failure.receipt=value.receipt;}
      throw failure;
    }
    if(!exact(value,['binding','project_id','checkpoint','value'])||value.binding!==binding||value.project_id!==project||!sha(value.checkpoint)||(!definition.mutation&&value.checkpoint!==cp)||!value.value||typeof value.value!=='object'||Array.isArray(value.value)){
      const failure=Error('Saved response belongs to a different project or checkpoint. Refresh project status.');failure.code='transport';throw failure;
    }
    if(m2PagedActions.has(action)){
      const page=value.value,limit=arguments_.limit??(m2HistoryActions.has(action)?1:40),offset=arguments_.offset??0;
      if(!Array.isArray(page.items)||page.items.length>limit||page.offset!==offset||page.limit!==limit||!Number.isSafeInteger(page.total)||page.total<0||page.items.length!==Math.min(limit,Math.max(0,page.total-offset))){const failure=Error('Saved page differs from its requested continuation.');failure.code='transport';throw failure;}
    }
    if(definition.mutation){state={...state,project:{...state.project,checkpoint:value.checkpoint}};pending=null;showState();}
    return value.value;
  }
  async function explore(ticket,more=false){
    const action=$('project-explore-kind').value,offset=more?exploreOffset:0,args={offset,limit:40};
    if(['policies','lineage'].includes(action))args.origin_catalog_id=state.project.project_id;
    if(action==='producers')args.family=$('project-producer-family').value;
    if(action==='data_query'){if($('project-data-search').value)args.q=$('project-data-search').value;if($('project-data-kind').value)args.kind=$('project-data-kind').value;}
    const value=await m2Request(action,args,ticket);if(!value)return;
    if(!more)$('project-explore-list').replaceChildren();
    for(const item of value.items){
      const row=document.createElement('li'),button=document.createElement('button');button.type='button';
      const fact=item.study??item.run??item.current??item.value??item,origin=item.origin_catalog_id??fact.ref?.catalog_id??state.project.project_id;
      button.textContent=[fact.name??fact.id??item.sha256??item.id??'Saved record',fact.kind??fact.format??item.family??'',fact.state??fact.review??item.availability?.status??'',fact.revision?`revision ${fact.revision}`:''].filter(Boolean).join(' · ');
      button.onclick=()=>run(ticket=>inspectItem(action,item,origin,ticket),{clean:true});row.append(button);$('project-explore-list').append(row);
    }
    exploreOffset=value.offset+value.items.length;exploreTotal=value.total;$('project-explore-more').hidden=exploreOffset>=exploreTotal;
    $('project-explore-summary').textContent=`Showing ${value.total?offset+1:0}–${exploreOffset} of ${exploreTotal} saved records.`;
  }
  async function inspectItem(category,item,origin,ticket){
    const fact=item.study??item.run??item.current??item.value??item;
    const entry={category,origin,id:fact.id??item.id,value:fact,checkpoint:checkpoint()};
    const request={data_query:['data_get','record_id'],models:['model_get','model_id'],graphs:['graph_get','graph_id'],recipes:['recipe_get','recipe_id'],studies:['study','study_id'],runs:['run','run_id'],selections:['selection_get','selection_id']}[category];
    let detail=fact;
    if(category==='producers'){detail=await m2Request('producer',{origin_catalog_id:origin,producer_id:entry.id,family:$('project-producer-family').value},ticket);if(!detail)return;}
    if(request){const args={[request[1]]:entry.id};if(['studies','runs'].includes(category))args.origin_catalog_id=origin;detail=await m2Request(request[0],args,ticket);if(!detail)return;}
    clearExplorationDetail();entry.value=detail.study??detail;entry.saveAction={models:'model_save',graphs:'graph_save',recipes:'recipe_save',studies:'study_save'}[category];explored=entry;
    $('project-detail-title').textContent=entry.value.name??`${category==='runs'?'Historical Run':'Saved record'} ${entry.id??''}`;
    $('project-detail-facts').append(projectValue(detail));
    if(category==='artifacts'){entry.artifactSha=detail.sha256;$('project-artifact-status').hidden=false;artifactResolutionForm(detail.availability?.state);}
    if(category==='models')$('project-model-publish').hidden=false;
    if(entry.saveAction&&origin===state.project.project_id){$('project-metadata-form').hidden=false;$('project-metadata-name').value=entry.value.name??'';}
    if(category==='data_query'){
      $('project-detail-history').hidden=false;$('project-detail-availability').hidden=false;$('project-rights-form').hidden=false;$('project-selection-form').hidden=false;
      $('project-rights-note').value=entry.value.provenance?.rights_note_correction?.note??entry.value.provenance?.rights??'unknown';
      const key=entry.value.task?.endsWith('_classification')?'label':entry.value.task==='image_caption'?'caption':entry.value.task==='text_corpus'||['sequence','mesh','pointcloud','volume','field_sequence'].includes(entry.value.kind)?'note':null;
      if(key){entry.annotationKey=key;$('project-data-note-form').hidden=false;$('project-data-note').value=entry.value.annotation?.[key]??'';$('project-data-note-help').textContent=`${entry.value.task.replaceAll('_',' ')} · save a ${key==='label'?'class label':key}.`;$('project-data-note').maxLength=key==='label'?80:4000;$('project-data-review').value=entry.value.review==='human_reviewed'?'human_reviewed':'draft';}
    }
    if(category==='runs'){entry.document=detail.document;$('project-run-document').hidden=!detail.document;$('project-run-evidence').hidden=false;$('project-run-disclose').hidden=!selectedContracts.has('project_files.expose_holdout');$('project-disclosure-label').hidden=$('project-run-disclose').hidden;}
    controls();$('project-detail-title').focus();
  }
  function clearExplorationDetail(){
    explored=null;historyOffset=0;historyTotal=0;$('project-detail-facts').replaceChildren();$('project-detail-history-list').replaceChildren();
    for(const name of ['project-metadata-form','project-data-note-form','project-rights-form','project-selection-form','project-detail-history','project-detail-history-more','project-detail-availability','project-run-evidence','project-run-document','project-run-disclose','project-disclosure-label','project-model-publish','project-artifact-status','project-artifact-resolve-form'])$(name).hidden=true;
  }
  async function dataHistory(ticket,more=false){
    if(!explored||explored.category!=='data_query')throw Error('Select saved data first.');
    const value=await m2Request('data_history',{record_id:explored.id,offset:more?historyOffset:0,limit:1},ticket);if(!value)return;
    if(!more)$('project-detail-history-list').replaceChildren();
    for(const snapshot of value.items){const row=document.createElement('li');row.append(projectValue(snapshot));$('project-detail-history-list').append(row);}
    historyOffset=value.offset+value.items.length;historyTotal=value.total;$('project-detail-history-more').hidden=historyOffset>=historyTotal;
    message(`Saved revisions loaded: ${historyOffset} of ${historyTotal}.`);
  }
  async function metadataSaved(ticket,action,args){
    const value=await m2Request(action,args,ticket);if(!value)return;
    const form={model_save:'project-metadata-form',graph_save:'project-metadata-form',recipe_save:'project-metadata-form',study_save:'project-metadata-form',data_annotate:'project-data-note-form',data_rights:'project-rights-form',selection_create:'project-selection-form',search_create:'project-search-form',data_import_image:'project-source-form',data_import_audio:'project-source-form',model_create:'project-model-create-form',study_create:'project-study-create-form',data_import_scientific:'project-scientific-form'}[action];
    if(form)for(const field of $(form).querySelectorAll('input'))if(!['number','file'].includes(field.type))field.value='';
    m2DirtyForms.delete(form);m2Dirty=m2DirtyForms.size>0;
    if(!m2Dirty)clearExplorationDetail();await query(ticket);message('Change saved to the project. Load saved records to inspect the new revision.');controls();
  }
  $('project-explore-load').onclick=()=>run(ticket=>explore(ticket),{clean:true});
  $('project-explore-more').onclick=()=>run(ticket=>explore(ticket,true),{clean:true});
  $('project-detail-history').onclick=()=>run(ticket=>dataHistory(ticket));
  $('project-detail-history-more').onclick=()=>run(ticket=>dataHistory(ticket,true));
  function artifactResolutionForm(availability){
    $('project-artifact-resolve-form').hidden=availability!=='missing';
    const roots=$('project-artifact-root'),previous=roots.value;roots.replaceChildren();
    for(const root of state.roots){const option=document.createElement('option');option.value=root;option.textContent=root;roots.append(option);}
    if(state.roots.includes(previous))roots.value=previous;
  }
  async function artifactStatus(ticket){
    if(!explored?.artifactSha)throw Error('Select a saved artifact first.');
    const value=await m2Request('artifact_status',{sha256:explored.artifactSha},ticket);if(!value)return;
    $('project-detail-facts').append(projectValue(value));artifactResolutionForm(value.state);controls();
  }
  $('project-artifact-status').onclick=()=>run(artifactStatus);
  $('project-artifact-resolve-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(!explored?.artifactSha)throw Error('Select a missing artifact first.');
    const expected=explored.artifactSha,value=await m2Request('artifact_resolve',{sha256:expected,root:$('project-artifact-root').value,path:$('project-artifact-path').value},ticket);if(!value)return;
    if(value.format!=='project_artifact_resolution_v1'||value.sha256!==expected)throw Error('Artifact resolution observation differs from this artifact.');
    m2DirtyForms.delete('project-artifact-resolve-form');m2Dirty=m2DirtyForms.size>0;$('project-artifact-path').value='';
    $('project-detail-facts').append(projectValue(value));await artifactStatus(ticket);message('Artifact resolution observation saved. Current availability refreshed.');
  });};
  for(const field of ['project-artifact-root','project-artifact-path'])$(field).addEventListener('input',()=>{m2DirtyForms.add('project-artifact-resolve-form');m2Dirty=true;controls();});
  $('project-detail-availability').onclick=()=>run(async ticket=>{const value=await m2Request('data_availability',{record_id:explored.id},ticket);if(value)$('project-detail-facts').append(projectValue(value));});
  $('project-run-evidence').onclick=()=>run(async ticket=>{const value=await m2Request('evidence',{run_id:explored.id,origin_catalog_id:explored.origin},ticket);if(value){$('project-detail-facts').append(projectValue(value));message('Retained evidence read through current disclosure and integrity checks.');}});
  $('project-run-disclose').onclick=()=>run(async ticket=>{const value=await m2Request('expose_holdout',{run_id:explored.id,origin_catalog_id:explored.origin,reason:$('project-disclosure-reason').value},ticket);if(value){$('project-detail-facts').append(projectValue(value));message('Held-out disclosure allowed for this Run on this installation.');}},{clean:true});
  $('project-metadata-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const value=explored.value,name=$('project-metadata-name').value;if(!str(name,120))throw Error('Enter a name up to 120 characters.');
    const args=explored.category==='studies'?{study_id:explored.id,revision:value.revision,name,limits:value.limits,policy:value.policy}:{[{models:'model_id',graphs:'graph_id',recipes:'recipe_id'}[explored.category]]:explored.id,revision:value.revision,document:{...value,name}};
    await metadataSaved(ticket,explored.saveAction,args);
  });};
  $('project-data-note-form').onsubmit=event=>{event.preventDefault();run(ticket=>metadataSaved(ticket,'data_annotate',{record_id:explored.id,revision:explored.value.revision,source_revision:explored.value.source_revision,task:explored.value.task,annotation:{[explored.annotationKey]:$('project-data-note').value},groups:explored.value.groups,review:$('project-data-review').value}));};
  $('project-rights-form').onsubmit=event=>{event.preventDefault();run(ticket=>metadataSaved(ticket,'data_rights',{record_id:explored.id,revision:explored.value.revision,source_revision:explored.value.source_revision,note:$('project-rights-note').value}));};
  $('project-selection-form').onsubmit=event=>{event.preventDefault();run(ticket=>metadataSaved(ticket,'selection_create',{document:{name:$('project-selection-name').value,items:[{id:explored.id,revision:explored.value.revision,source_revision:explored.value.source_revision}]}}));};
  $('project-search-form').onsubmit=event=>{event.preventDefault();run(ticket=>metadataSaved(ticket,'search_create',{document:{name:$('project-search-name').value,criteria:{q:$('project-data-search').value,kind:$('project-data-kind').value,review:'',sort:'',task:'',label:'',group:'',rights:''}}}));};
  $('project-source-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const file=$('project-source-file').files?.[0];if(!file||file.size>524288)throw Error('Choose a source file of at most 512 KiB.');
    const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(const byte of bytes)raw+=String.fromCharCode(byte);
    if(ticket!==epoch)return;
    const kind=$('project-source-kind').value,args={name:$('project-source-name').value,groups:groups($('project-source-groups').value),rights:$('project-source-rights').value,[kind==='audio'?'wav':'image']:btoa(raw)};
    await metadataSaved(ticket,'data_import_'+kind,args);$('project-source-file').value='';$('project-source-name').value='';
  });};
  for(const field of ['project-metadata-name','project-data-note','project-data-review','project-rights-note','project-selection-name','project-search-name','project-source-file','project-source-name','project-source-groups','project-source-rights'])$(field).addEventListener('input',()=>{const form=field.startsWith('project-source-')?'project-source-form':field.startsWith('project-metadata-')?'project-metadata-form':field.startsWith('project-data-')?'project-data-note-form':field.startsWith('project-rights-')?'project-rights-form':field.startsWith('project-selection-')?'project-selection-form':'project-search-form';m2DirtyForms.add(form);m2Dirty=true;controls();});
  $('project-source-kind').addEventListener('change',()=>{m2DirtyForms.add('project-source-form');m2Dirty=true;controls();});
  $('project-explore-kind').addEventListener('change',controls);
  $('project-definitions-load').onclick=()=>run(async ticket=>{
    const value=await m2Request('definitions',{},ticket);if(!value)return;
    if(!Array.isArray(value.recipes))throw Error('No model template definitions are available.');
    modelTemplates=value.recipes.filter(item=>item.model_template).map(item=>item.model_template);templateBinding=state.binding;
    $('project-model-template').replaceChildren();
    for(const [index,template] of modelTemplates.entries()){const option=document.createElement('option');option.value=String(index);option.textContent=template.name;$('project-model-template').append(option);}
    controls();message(modelTemplates.length?'Available model templates loaded.':'This installation has no model templates.');
  },{clean:true});
  $('project-model-create-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(templateBinding!==state.binding)throw Error('Load model templates for this project first.');
    const template=modelTemplates[Number($('project-model-template').value)];if(!template)throw Error('Choose a model template.');
    const document=JSON.parse(JSON.stringify(template));document.name=$('project-model-create-name').value;
    await metadataSaved(ticket,'model_create',document);
  });};
  $('project-model-publish').onclick=()=>run(ticket=>metadataSaved(ticket,'model_publish',{model_id:explored.id,revision:explored.value.revision}),{clean:true});
  for(const field of ['project-model-template','project-model-create-name'])$(field).addEventListener('input',()=>{m2DirtyForms.add('project-model-create-form');m2Dirty=true;controls();});
  $('project-study-create-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const limits={};for(const [key,field] of [['attempt_slots','attempts'],['admitted_wall_seconds','seconds'],['retained_bytes','retained'],['peak_staging_bytes','staging']]){const value=Number($('project-study-'+field).value);if(!Number.isSafeInteger(value)||value<1)throw Error('Study budget values must be positive whole numbers.');limits[key]=value;}
    const metric=$('project-study-metric').value;if(!sha(metric))throw Error('Use the exact SHA256 of a saved metric definition.');
    await metadataSaved(ticket,'study_create',{name:$('project-study-create-name').value,limits,policy:{format:'selection_policy_v1',metric_definition_sha256:metric,checkpoint_rule:$('project-study-checkpoint').value,replicate_reduce:$('project-study-replicates').value,required_capabilities:[],numerical_acceptance:$('project-study-numerical').value,tie_break:'trial_id'}});
  });};
  function scientificReferenceHash(reference){
    if(reference.status!=='available'||!sha(reference.observed_sha256))return null;
    if(Object.hasOwn(reference,'sha256'))return sha(reference.sha256)&&reference.integrity==='verified'&&reference.observed_sha256===reference.sha256?reference.observed_sha256:null;
    return reference.integrity==='unverified'?reference.observed_sha256:null;
  }
  async function sourceReferences(ticket,more){
    if(!registeredSource||registeredSource.binding!==state.binding)throw Error('Register this source for the current project binding first.');
    const {origin_catalog_id,project_id,manifest_sha256}=registeredSource;
    const value=await m2Request('source_references',{origin_catalog_id,project_id,manifest_sha256,offset:more?registeredSource.next_offset:0,limit:40},ticket);if(!value)return;
    if(!more){registeredSource.references=[];$('project-scientific-reference').replaceChildren();}
    for(const reference of value.items){
      registeredSource.references.push(reference);const observed=scientificReferenceHash(reference),option=document.createElement('option');option.value=reference.id;option.disabled=observed===null;
      const integrity=observed?(Object.hasOwn(reference,'sha256')?'declared digest verified':'observed digest unverified; not pinned in the manifest'):(reference.integrity==='mismatch'?'declared digest mismatch':reference.status??'unavailable');
      option.textContent=`${reference.label??reference.id} · ${integrity}`;$('project-scientific-reference').append(option);
    }
    registeredSource.next_offset=value.offset+value.items.length;$('project-source-references-more').hidden=registeredSource.next_offset>=value.total;
  }
  $('project-source-references-more').onclick=()=>run(ticket=>sourceReferences(ticket,true));
  $('project-run-document').onclick=()=>run(async ticket=>{
    const descriptor=explored?.document;if(!descriptor||!sha(descriptor.sha256)||!Number.isSafeInteger(descriptor.bytes)||descriptor.bytes<0||descriptor.bytes>64*1024*1024)throw Error('This retained document cannot be downloaded in this browser. Use its exact project API segments.');
    const pieces=[];let offset=0;
    do{
      const limit=262144,value=await m2Request('run_document_segment',{run_id:explored.id,origin_catalog_id:explored.origin,expected_sha256:descriptor.sha256,offset,limit},ticket);if(!value)return;
      if(value.format!=='project_run_document_segment_v1'||value.origin_catalog_id!==explored.origin||value.run_id!==explored.id||value.sha256!==descriptor.sha256||value.bytes!==descriptor.bytes||value.offset!==offset||value.limit!==limit||typeof value.base64!=='string')throw Error('Retained document segment differs from the selected document.');
      const raw=atob(value.base64),bytes=Uint8Array.from(raw,char=>char.charCodeAt(0));
      if(bytes.length!==Math.min(limit,descriptor.bytes-offset)||value.next_offset!==(offset+bytes.length<descriptor.bytes?offset+bytes.length:null))throw Error('Retained document continuation differs.');
      pieces.push(bytes);offset+=bytes.length;
    }while(offset<descriptor.bytes);
    const blob=new Blob(pieces,{type:'application/json'}),hash=new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()));
    if(ticket!==epoch)return;
    if(Array.from(hash,byte=>byte.toString(16).padStart(2,'0')).join('')!==descriptor.sha256)throw Error('Retained document integrity differs; no download was created.');
    const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;link.download='retained-run-'+explored.id+'.json';link.click();URL.revokeObjectURL(url);message('Exact retained Run document downloaded and verified.');
  });
  $('project-register-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const value=await m2Request('source_register',{root:$('project-files-root').value,manifest_path:$('project-register-path').value},ticket);if(!value)return;
    if(!id(value.project_id)||!id(value.origin_catalog_id)||!sha(value.manifest_sha256))throw Error('The registered source identity is unavailable.');
    registeredSource={binding:state.binding,origin_catalog_id:value.origin_catalog_id,project_id:value.project_id,manifest_sha256:value.manifest_sha256,references:[],next_offset:0};
    await sourceReferences(ticket,false);
    m2DirtyForms.delete('project-register-form');m2Dirty=m2DirtyForms.size>0;controls();message('Source manifest saved. Select one exact declared data reference to import.');
  });};
  $('project-scientific-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(!registeredSource||registeredSource.binding!==state.binding)throw Error('Register a local source for this project binding first.');
    const reference=registeredSource.references.find(item=>item.id===$('project-scientific-reference').value),observed=reference&&scientificReferenceHash(reference);if(!observed)throw Error('Choose an available data reference with a current observed digest. Declared digests must match and be verified.');
    const {origin_catalog_id,project_id,manifest_sha256}=registeredSource;
    await metadataSaved(ticket,'data_import_scientific',{snapshot:{origin_catalog_id,project_id,manifest_sha256},reference_id:reference.id,expected_sha256:observed,document:{name:$('project-scientific-name').value,groups:groups($('project-scientific-groups').value),rights:$('project-scientific-rights').value}});
  });};
  for(const [form,fields] of [['project-study-create-form',['project-study-create-name','project-study-metric','project-study-attempts','project-study-seconds','project-study-retained','project-study-staging','project-study-checkpoint','project-study-replicates','project-study-numerical']],['project-register-form',['project-register-path']],['project-scientific-form',['project-scientific-reference','project-scientific-name','project-scientific-groups','project-scientific-rights']]])for(const field of fields)$(field).addEventListener('input',()=>{m2DirtyForms.add(form);m2Dirty=true;controls();});
  for(const action of ['new','open','save','close'])$('project-files-'+action).onclick=()=>lifecycle(action);
  $('project-files-refresh').onclick=refresh;
  $('records-more').onclick=()=>run(async ticket=>{await query(ticket,true);message('More text records loaded.');return nextRecord===null?$('records-title'):$('records-more');});
  $('record-history-more').onclick=olderHistory;
  $('project-files-discard').onclick=()=>{importDirty=false;annotationDirty=false;m2Dirty=false;m2DirtyForms.clear();$('project-artifact-path').value='';for(const form of ['project-model-create-form','project-study-create-form','project-register-form','project-scientific-form'])for(const field of $(form).querySelectorAll('input'))field.value=field.defaultValue??'';clearExplorationDetail();$('project-source-file').value='';$('project-source-name').value='';$('project-search-name').value='';$('project-selection-name').value='';$('text-name').value='';$('text-content').value='';$('text-groups').value='project';$('text-rights').value='unknown';showRecord();clearError();message('Unsubmitted edits discarded. Saved project records are unchanged.');};
  for(const field of ['text-name','text-content','text-groups','text-rights'])$(field).addEventListener('input',()=>{importDirty=true;controls();});
  for(const field of ['annotation-value','annotation-groups','record-review','annotation-task'])$(field).addEventListener(field==='annotation-task'||field==='record-review'?'change':'input',()=>{annotationDirty=true;annotationHelp();controls();});
  window.addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});
  window.addEventListener('tuldok-session',()=>{++epoch;busy=false;blocked=true;selectedContracts=new Set();controls();message('Session changed. Refreshing project status; your unsubmitted edits remain here.');refresh();});
  controls();refresh();
})();
