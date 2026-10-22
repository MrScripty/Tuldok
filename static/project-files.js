'use strict';
// One page owns this projection. The server owns project state and every edit.
(()=>{
  const $=id=>document.getElementById(id), base='/api/workspace/project-files';
  const actions=['new','open','save','close','query','get','import_text','annotate'];
  const tasks=['text_classification','text_entities','text_corpus'];
  // Generated from agent_api; freshness is checked by the client contract tests.
  const pins = /* PROJECT_FILES_CONTRACTS_START */
{
  "project_files.annotate": "70feae2ad14c49c4ae95b5bb69b4a50fbf93191cde840544cf89b6cbe8dc5c58",
  "project_files.artifact_resolve": "0df477e294b4e0729a707d7dfb6038414fc354e1ae50155eaacfa82b3a55f51f",
  "project_files.artifact_status": "8dd0343f5f882c96cf023f8274734ca57175ae986e82b3bb1188cb5864784834",
  "project_files.artifacts": "20a4031d189058721d09b8bf694ea9b1583eea410afd381f58fe6c70d0a0c339",
  "project_files.candidate": "c519ff04bc06d5e538d36b7f278862d8f282d0e7b97dd7f262444c384a50f854",
  "project_files.candidate_select": "f043be6923760a208ca50d02a1ff4b60eadf09d48a034acdb18749806a537080",
  "project_files.close": "95d0099ec2a378a1bbb65676799dd3baae2f36b838301f7aa165b116fba5edf6",
  "project_files.data_annotate": "289270f5cb946765c5ced22fbbd18765bb55743145014c81cf54d7a6ba3025ea",
  "project_files.data_availability": "92332c04973a4fa45d47e384717152ebc4a9ca08e7eb487669688ccd2ed42cbb",
  "project_files.data_get": "0d19505995cbd8c12e3938cd89cf05955a2a63488a220711d29dd24b27c0c8c8",
  "project_files.data_history": "b9e9e13389befe5f531d33d4d4d893649cb076f3eff98aa6ee85a4c46f03148a",
  "project_files.data_import_audio": "51b511a068bed6ec024bd70bf08a48a23a94906362d54e0f3eb1223e325c237e",
  "project_files.data_import_image": "e9f86ce62d29d267090c7955e0deb084f6ad6a936d1418baf5d807aa6d84ea3e",
  "project_files.data_import_mesh": "840d6e1d6ab326d144b63e275d60d304277b5d4867c9c170c6dde5e117b46107",
  "project_files.data_import_pointcloud": "c171b1342a5844fc1862947e20ae675395b8c3e24b44bff1179e0e8e6df70f53",
  "project_files.data_import_scientific": "a39ce46384bb2f0c3cdb9a6bbf881316ce166a26208fc41b4a88bb307af32d63",
  "project_files.data_import_sequence": "da8b91c9fd76d951fddc33acf6cca56287e0d7a29319b46032629b777af1f1ee",
  "project_files.data_import_text": "c2db90c749154cb5489e13494d5a4404fdaf5a14895679fe2075fdfdc39e899d",
  "project_files.data_import_volume": "c6e509d797970afd7da9e2069c29736e290ada8e7034326b31e1cb707aa572e2",
  "project_files.data_preference_delete": "900538c7d8f74f04ed93387a864c8235b4162902345f6864b8d325527f63da5f",
  "project_files.data_preference_history": "5ee7d60ce5e4aa09ea3496e9212b3404820d619cc2d47425faa94a3506d9ad07",
  "project_files.data_preference_save": "eacdaa8b32cac556f8a591c4ca3f1191d83182623bd425a5619e1c6920c17782",
  "project_files.data_preferences": "35b9bff0cba8bf453d446a8b62a6d003cc49f6abb8a12b55bfb76a112c3f2067",
  "project_files.data_query": "0a7585ed5c41ed28eee2505e95773741a7af82c74b5265b8ed4ebf2beb72e394",
  "project_files.data_response_history": "1bd46a162efae7213ff7c8a7b77dfe843e952a629fd7c24af3b5298e04140224",
  "project_files.data_response_save": "fa5b92afe529520fe8206d629bd88085a68f4f9b399cd40dd05fd3948d3592f0",
  "project_files.data_responses": "3e0c009244cad04fca4356cf3647bfd2b42cfc0d6a2ac31bb8de25cdb3c60ec8",
  "project_files.data_rights": "ead16cca68b03533daa81bf06148e1918ce40dbc823ee060bd9908581f788653",
  "project_files.data_source_delete": "457618e618cca92a71b668ffb9f68b0db87e51c417c2e5f41dcde76d71a23985",
  "project_files.data_source_save": "0d50c45d445b2ce1014a696c3bc95965f0b548ded939f4a650f985f34e1ce849",
  "project_files.definitions": "3516fcf8764382780c7da699218a05ff1f811634656cc81722ef547f21159698",
  "project_files.dependencies": "615e173c6e7cb811dc5e51ef6c368975b4dd06de14d6cf69fbd8c4bb01e3f9e4",
  "project_files.evidence": "440d7dba608d633a4a42479018360ef2fa6609a47148e7edfdf5246f84c020ef",
  "project_files.execution_approve_external": "b35cec1a8bc5faad9e437ee04b6fb3bc9d575e8b7c4dd0444401fa8f551fa301",
  "project_files.execution_cancel": "5fff1a68bfaeefcf426c573f4f128e76c96163171f31580922be3178080ffcd0",
  "project_files.execution_generation_resume": "cfadef988f4510fcea1e64e1a8a4ca60794bec26a2d1c116b35e678971cc33ae",
  "project_files.execution_grounded_review": "de971104eebe46acb67edfb77f1c0df98e8302528ef446ad51c772c13e67458b",
  "project_files.execution_health": "c3b1d0017f5a49cf69c3a4c5c33e1d3db9846404d12627563d97ef40de7404a5",
  "project_files.execution_preflight_external": "f754d712ac7da823375408fbcec63f7006c972a6e0885d69bae6772f2b850fea",
  "project_files.execution_producer_cancel": "af114f7ed941f80ec565577863a6fffc4ec1c7d7069af6715350e8489526fd61",
  "project_files.execution_producer_decide": "38bd7d1a1a052d62f6fc74cc16fcaf9e3c243f97dc3c39e38cdef03ca272a5d8",
  "project_files.execution_producer_health": "297c6160a07cef60a8d4a50a690805f30a75b7e1bf6543e6da3a7befcb133b7e",
  "project_files.execution_producer_start": "e7ee70a06346026980ba0fbf808b6d61ff3e7ac57a6619d72cd1b8b77e9662f7",
  "project_files.execution_reconcile_current": "5ed3f998f053fd6333804e604f758c58e1b862c6f92f4de4272495916cef77de",
  "project_files.execution_study_abandon_preparation": "650e7f85ea3ff476448422077ecc51fc06e270e975967886d5a6c726aee5af73",
  "project_files.execution_study_admit": "381cacfa7582db321520cbc0d0e0be6bd187e1e3ff98cdbde371244b5994adba",
  "project_files.execution_study_approve": "0a49e0d1b8e789a96969b73565f127d5cbb2c6cc39fea40fff33029f2ddbd7e2",
  "project_files.execution_study_continue": "d421a59a95fb2a6b8d4e65d652000a13177054d34bafff3d0a3e30eeae00fb75",
  "project_files.execution_study_prepare_package": "6687819b4cad1fa89ca1ec874422ea04f52cbc3685691dc3c612f122933c89b2",
  "project_files.execution_study_prepare_verifier": "1c28024ab764c1f5747f17b90e73a95fb1666be4f94af040f376ec6241e12421",
  "project_files.execution_study_reconcile_preparation": "c5a301fd6e3159de684f5700d557ccd13dd704e617d4779015e9b5ca93d76075",
  "project_files.execution_study_stop": "84d103019c80b8e7bd3b59e0259c3947de4f4f48cc05c3076cf16112d8671911",
  "project_files.execution_submit_external": "fc33d4eac346c1f08423ccb5d593db43b561124629d53f2a8896ff9838db99f3",
  "project_files.expose_holdout": "d69478ed54267ee1f1966f423f412a32f90b95a55997c6dc7d8348e3cdd78fd7",
  "project_files.file_adopt": "a190326d5c54296f8359be594996908fa28acbbd125168821c3fa1f520ef9b07",
  "project_files.file_adopt_deletion": "7b6d661856a614d1b83d8011d1ffc7f9e2619853495faf9250888739f880685c",
  "project_files.file_get": "a22c27e2fd890ffcb479e0aa8ea40a0cb32d06d1e5750b970b40f27915fe4d24",
  "project_files.file_history": "c83477f7b0f8616c96ad79cebaf0eb3887fe289567f5d5ceb1d1502bebed7423",
  "project_files.files_inspect": "0c2ff3ed93109ea19b5c92ffa24ac8f67e4bcfa3fe386921e984b5dfa3bfe7eb",
  "project_files.fork_info": "958bc1aa269b5459c7e2d9c6bcb6725c06f7055502d73c49a95330cc4065aea4",
  "project_files.get": "6b0f4e16a00aa119b86cbb5493be0bac945ff08a5e63773a8f2c2f9296658d5b",
  "project_files.graph_clone": "8f9b460530f0f136900734345fc338a1993ffdaddf5f4d90faf352c39f397514",
  "project_files.graph_create": "8fcb6d573b849ac03b5ee0ae192f274c11b9b5303451410ee46013f4cb0d83dc",
  "project_files.graph_create_external": "93d88731f66062c9d0ac15d38897e731e25e39df7f9b141e5f3277f2d07b4205",
  "project_files.graph_get": "77eea46e63758f0ca172cd23595cf5a42fe9820dbc82f3aefb7f5b6c22dc23d9",
  "project_files.graph_save": "5a9745e4041cda6be46f63b83cb1f89d102d10c8810e41261a326cf0ef6821f4",
  "project_files.graphs": "4892c990da89bc193d408537761e2e2db19694840ee652e64cba64a3bf57dbdb",
  "project_files.import_text": "0f168320abb858892a2724b0b59862475bec653d1670ce754d61f2d82c912538",
  "project_files.lineage": "750c173b42b113b6b82542fe4d82f8652cf07e1efe5cafde4c3e776d6afc3683",
  "project_files.lineage_record": "16fd6cbd20bcd3743e4ac889dc6c398e714152f57d3c65cbd013f047c4267708",
  "project_files.material_intent": "79d1ee6c3d8bc1313f2e51ff1d7d4ea489f5f3e82a6fd2e00ed93e1f7613bfbd",
  "project_files.material_intent_capabilities": "86e90e2d0f094beb1c277a680da9a35e28d78c827390ac1c4e51fc3003c1ce32",
  "project_files.material_intents": "6431fd2780d706c77d2c4dd82f15794017368fd3bade28ac62bbdff5c8b0c547",
  "project_files.materials": "92a6a6a1750fed89aef9574ab6e82be2c6c6351bfa89fbfcb1f3866d4ea3cb13",
  "project_files.model_create": "34cf790fb2a3355ccab7c3a6c7174ced8dae861812d9479582fd8d5a9212745c",
  "project_files.model_get": "95cc198ab6f084b596324f7251803ad4670a9f8e786e1a9639f1b9ed041798c3",
  "project_files.model_material": "46afde2b06e0e5b08565f12ec86d2d7ec43ef6b63d97c86c264fc9c2f451f20b",
  "project_files.model_publish": "97c0ec706fd663d322764a2dd72bd920e7e7ac8defaee2d23624502ed239fc62",
  "project_files.model_save": "a90f8d985578191dee672824c9178559452f8b0dd759f74ed91337a96ca670e8",
  "project_files.models": "92e13621050d7f229a4785ed6845df2f191a9e037bcdf377fa7fb0ba796aebe3",
  "project_files.native_preflight": "494c907dac56a3126d26f064ec20bb980f918bded8e7f727c1fdaaa118059b13",
  "project_files.native_reconcile": "74299207459fbd08d23ad7e8c1db205a4297f014415fd463c9857ba60dda4c7e",
  "project_files.native_retry": "489655b49dadc184d95d6455ad2662bd5e7fd2cde2170fd303a92b2de77471c1",
  "project_files.native_submit": "82468f35f04306fd4f39a0cc94a487fc05ae739e28f24f0be49ed35644639643",
  "project_files.new": "672373f8ddc0b89fea15165798aab97cf4ac2cdf678a04d96839512cc8976b6f",
  "project_files.open": "fd4b9f97c03cd7050981cfafd1177bff8c86351bb603b8f7980aaa149d2b0368",
  "project_files.package_state": "6f0369eafab3b8ed1db71ffb12e7d5a2bbcf400b46315d46ba1e2fb13e63baf7",
  "project_files.policies": "629b61ae9bd9c65d04cd3e89fb50fb62dd455b9f75bcaf9db08b7890bb5516f5",
  "project_files.policy": "5bdb86600f2ec387fde721b22fdd0afa3ed47660126847c2908c1bb9de0421cb",
  "project_files.producer": "6187a9eb1e32cb3bcf13d283492b1ad909c32753aa5ed97fbc12a9708523d9e3",
  "project_files.producers": "65b2f4dff355c3bf5a023bf4f9dc116e302eda85ad90e6afaa2f21f0aa0667b5",
  "project_files.publication_result": "10b4a5f3d4f37343322327024ddbedf5b6b69672c785e208ec48534d7b40c867",
  "project_files.query": "9a8b0d3a99adf5d7d53b62261dfac83e8b3ea44c10cb2f6c7a9c3d79422fef08",
  "project_files.recipe_create": "53a6760f03675d4d8a8d3a0ffd5b56689975667bbc136b1edf8a206307c18651",
  "project_files.recipe_get": "23837c51032b7c7ae6a365616f66cab9ae0d191108027291ad49898b2c421e2a",
  "project_files.recipe_material": "c384acbf2333d7dd360991d72c8e1e218dc3ad3291af76e09f76efe25ea69cc0",
  "project_files.recipe_prepare": "e91344f3032bf3e6abf50e5f5399252439498bce999c1f732322fd70a5eda1cf",
  "project_files.recipe_save": "7fb9708aaba280ae437ee2554ecdaef3f724f3a7f4e55b49e54e1ef186691a7e",
  "project_files.recipes": "3217c2033f60242c661c6689d6f9f634ea9d3a9b188a9465edcdc0bea572bc6c",
  "project_files.release_freeze": "93a1b5b3c6bf11f63c92571113ce536743e7fd07b0b77ae8aee6e909230245df",
  "project_files.release_preview": "0b6e2f0c2d7e3503fa29391fc20d27f058d0d3ad61e4547aee9845633ba6c5d8",
  "project_files.retained_analysis": "05959a0e49a623318d6d70ded4f86df5df5d9bf29c411fcfcd1d9c0148b650cc",
  "project_files.retained_analysis_export": "fa5d97e094484da053a1374131040deefdac429ec8360d671f57b12353d69359",
  "project_files.run": "3cd94d46587596c36da4d1187b4648442cf6f216d2972daa496b7879e294ddec",
  "project_files.run_document_segment": "bd6599cb89b106ba0be4141fc5d38ad5e07b2c57c5b24e1fcf91802ba9ff9006",
  "project_files.runs": "cab46b11c5376ba641a717ceb1ce2bbe3693b7ac264e41192849f8522eb5d61d",
  "project_files.runtime_abandon": "21086c2a92f23a8d42085678a7b99a69897bacb5e84341d482b0d2e9d6b69df8",
  "project_files.runtime_capture": "2d787e49e7f911820d4341b33b4738219fa773a783bb2fb5a674d05dbfbb173a",
  "project_files.runtime_inspect": "ece28c002151d36b9a415d4b7692536318765d1a7f742e3fd1f60c53b3a28204",
  "project_files.runtime_material": "da48c927442878373434e93bb97fc65fc7056bd8e5a4b97e8a18627eb768cb07",
  "project_files.runtime_sources": "6b94cbb5c712fbbea5645cbb64f8fd8b7f72c28042ddeacd96aaaad828a81460",
  "project_files.runtime_status": "80931340bab620ca52c05277bc0380c97b7e9191a808312caedabc30f4ab7e96",
  "project_files.save": "38572e376db36f81582dc6419fded35ff9d7c9185f5af2cdaafd74c94790f90a",
  "project_files.save_as": "2b0558049ca0055a9682bcda6eb81ce9f48358b7cf804b5d499067a5594e2d33",
  "project_files.search_create": "ae5c51158d849cda199cc007c42ea7a1cb62cd15a7ca8957bd32df813548e942",
  "project_files.search_delete": "518037dbe9464fd327df53f7801a3c1ba30bb822467c091a2bc684542a58495c",
  "project_files.search_rename": "78ca2aed2cd34c278ee1a9858dc76ebf8d39111de36bd48ada43f0407af5ff70",
  "project_files.searches": "061be81df13158c18c2a124419da07db9564b44c239c8ca80cbf65a7ad26c1bd",
  "project_files.selection_create": "87f60aeb83a497e7c6adab524f3ddc4776a6820497aa676f50ab3e1104b62ba2",
  "project_files.selection_delete": "cb021e6e1d7b4df1db1e4ca614067c3b26820737eca92dbc7168b3ff45b0894f",
  "project_files.selection_get": "c99e320815d54b60d0ddb3179a0ee62fa5eca938ac71011813296ce93bb085b0",
  "project_files.selection_rename": "7e3fe9853cc593e4c0464162b3c9137208500650a125a46704f1e38d49b6f5a1",
  "project_files.selections": "fd9cc6a94144a349232e99aa1ad4890cb7cb4b023de8bf4e8249374aa29ec39d",
  "project_files.snapshot": "1eacdfeb7843bc432d62c6a94890dc07f618074faecb5e22589df9c9377e5030",
  "project_files.source_references": "36a6d5b97efd63268d393b456e3bfec45cc696335acf652eff503b64a4ca0869",
  "project_files.source_register": "04390ea427cb9958f5a0a1118de5cf8f91434d12e9c241621cf11465d804c64e",
  "project_files.status": "1d0c4b64caaab8369d4addefd72e53cc8c7d0be4c07729fa04b358febe643b6a",
  "project_files.studies": "5c45e0938cef51c271d1e82b28e878bc831f5a9272773440e39022074e6e87b6",
  "project_files.study": "b268a20042efe9c8bc260f74309688dc7bbbd60486d30a33621a68e1a92fa3d7",
  "project_files.study_create": "8d2aac7c073a6a7b3ebb41227b5b466cf03606625404f93a59b325038a4ad7a1",
  "project_files.study_save": "5bf3fb814588fd7d9c35836e9d964a64481b3cc4169caf76cad6ce776ff0fe15",
  "project_files.trial": "79afa4bed6d0907f3d4116cc04cb784e94e5a24ab89725ec24f5d7bce70e869f",
  "project_files.trial_prepare": "e1f6973536fd4c356c4a92fc674d6766f7df0d8a113b8ee71bb05d0adc40b04f"
}
/* PROJECT_FILES_CONTRACTS_END */;
  // Generated fixed operation routes from agent_api; remote schemas are never executed.
  const versionPins = /* PROJECT_FILES_VERSIONS_START */
{
  "project_files.annotate": {
    "1": "70feae2ad14c49c4ae95b5bb69b4a50fbf93191cde840544cf89b6cbe8dc5c58",
    "2": "2ae39dd621161500061bc8f57bb465e90fed04cfaf921e0dc368f82bd50cd107"
  },
  "project_files.execution_health": {
    "1": "c3b1d0017f5a49cf69c3a4c5c33e1d3db9846404d12627563d97ef40de7404a5",
    "2": "6b7a834881da36960c0a0ee393c0c26e0d918b857d30791e8e5af79c2ae4a73e"
  },
  "project_files.get": {
    "1": "6b0f4e16a00aa119b86cbb5493be0bac945ff08a5e63773a8f2c2f9296658d5b",
    "2": "fdc0858fc03a0866bb743b04251ea5f9a3c1e6be1b211366db7e0652166736ea"
  }
}
/* PROJECT_FILES_VERSIONS_END */;
  let selectedVersions=new Map();
  const selectedHeader=operation=>operation+'/'+selectedVersions.get(operation)+'/'+(versionPins[operation]?.[selectedVersions.get(operation)]??pins[operation]);
  const m2Operations = /* PROJECT_FILES_ROUTES_START */
{
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
  "project_files.execution_approve_external": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/approvals",
    "mutation": true
  },
  "project_files.execution_cancel": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/runs/{run_id}/cancel",
    "mutation": true
  },
  "project_files.execution_generation_resume": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/generation/{producer_id}/resume",
    "mutation": true
  },
  "project_files.execution_grounded_review": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/grounded/{producer_id}/review",
    "mutation": true
  },
  "project_files.execution_health": {
    "method": "GET",
    "path": "/api/workspace/project-files/execution",
    "mutation": false
  },
  "project_files.execution_preflight_external": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/preflight",
    "mutation": false
  },
  "project_files.execution_producer_cancel": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/producers/{producer_id}/cancel",
    "mutation": true
  },
  "project_files.execution_producer_decide": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/producers/{producer_id}/decide",
    "mutation": true
  },
  "project_files.execution_producer_health": {
    "method": "GET",
    "path": "/api/workspace/project-files/execution/producers/health",
    "mutation": false
  },
  "project_files.execution_producer_start": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/producers",
    "mutation": true
  },
  "project_files.execution_reconcile_current": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/reconcile-current",
    "mutation": true
  },
  "project_files.execution_study_abandon_preparation": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/preparations/abandon",
    "mutation": true
  },
  "project_files.execution_study_admit": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/runs",
    "mutation": true
  },
  "project_files.execution_study_approve": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/approvals",
    "mutation": true
  },
  "project_files.execution_study_continue": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/continue",
    "mutation": true
  },
  "project_files.execution_study_prepare_package": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/packages",
    "mutation": true
  },
  "project_files.execution_study_prepare_verifier": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/verifiers",
    "mutation": true
  },
  "project_files.execution_study_reconcile_preparation": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/preparations/reconcile",
    "mutation": true
  },
  "project_files.execution_study_stop": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/studies/{study_id}/stop",
    "mutation": true
  },
  "project_files.execution_submit_external": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/runs",
    "mutation": true
  },
  "project_files.expose_holdout": {
    "method": "POST",
    "path": "/api/workspace/project-files/runs/{run_id}/disclose",
    "mutation": true
  },
  "project_files.file_adopt": {
    "method": "POST",
    "path": "/api/workspace/project-files/files/adopt",
    "mutation": true
  },
  "project_files.file_adopt_deletion": {
    "method": "POST",
    "path": "/api/workspace/project-files/files/adopt-deletion",
    "mutation": true
  },
  "project_files.file_get": {
    "method": "GET",
    "path": "/api/workspace/project-files/files/{file_id}",
    "mutation": false
  },
  "project_files.file_history": {
    "method": "GET",
    "path": "/api/workspace/project-files/files/{file_id}/history",
    "mutation": false
  },
  "project_files.files_inspect": {
    "method": "GET",
    "path": "/api/workspace/project-files/files",
    "mutation": false
  },
  "project_files.fork_info": {
    "method": "GET",
    "path": "/api/workspace/project-files/fork",
    "mutation": false
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
  "project_files.material_intent": {
    "method": "GET",
    "path": "/api/workspace/project-files/material-intents/{family}/{definition_id}",
    "mutation": false
  },
  "project_files.material_intent_capabilities": {
    "method": "GET",
    "path": "/api/workspace/project-files/material-intents/capabilities",
    "mutation": false
  },
  "project_files.material_intents": {
    "method": "GET",
    "path": "/api/workspace/project-files/material-intents",
    "mutation": false
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
  "project_files.native_preflight": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/native/preflight",
    "mutation": true
  },
  "project_files.native_reconcile": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/native/phases/{phase_id}/reconcile",
    "mutation": true
  },
  "project_files.native_retry": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/native/runs/{run_id}/retry",
    "mutation": true
  },
  "project_files.native_submit": {
    "method": "POST",
    "path": "/api/workspace/project-files/execution/native/runs",
    "mutation": true
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
  "project_files.runtime_abandon": {
    "method": "POST",
    "path": "/api/workspace/project-files/runtime/abandon",
    "mutation": true
  },
  "project_files.runtime_capture": {
    "method": "POST",
    "path": "/api/workspace/project-files/runtime/capture",
    "mutation": true
  },
  "project_files.runtime_inspect": {
    "method": "GET",
    "path": "/api/workspace/project-files/runtime/inspect",
    "mutation": false
  },
  "project_files.runtime_material": {
    "method": "POST",
    "path": "/api/workspace/project-files/materials/runtime",
    "mutation": false
  },
  "project_files.runtime_sources": {
    "method": "GET",
    "path": "/api/workspace/project-files/runtime/sources",
    "mutation": false
  },
  "project_files.runtime_status": {
    "method": "GET",
    "path": "/api/workspace/project-files/runtime/status",
    "mutation": false
  },
  "project_files.save_as": {
    "method": "POST",
    "path": "/api/workspace/project-files/save-as",
    "mutation": true
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
}
/* PROJECT_FILES_ROUTES_END */;
  let selectedContracts=new Set();
  let state=null, selected=null, history=[], summaries=[], nextRecord=null, nextHistory=null, epoch=0, busy=false, blocked=false;
  let importDirty=false, annotationDirty=false, m2Dirty=false, pending=null;
  let registeredSource=null,modelTemplates=[],templateBinding=null;
  let runtimeInspection=null,runtimePending=null,runtimeSourceOffset=0,runtimeSourceTotal=0,runtimeFileOffset=0,runtimeFileTotal=0;
  let forkPending=null,workingSelection=null,workingDeletion=null,workingOffset=0,workingTotal=0,workingHistoryOffset=0,workingHistoryTotal=0,intentsOffset=0,intentsTotal=0,forkOffset=0,forkTotal=0,intentCapsOffset=0,intentCapsTotal=0;
  let nativeGraphs=[],nativePrepared=null,nativePending=null,nativeOffset=0,nativeTotal=0;
  let executionGraphs=[],executionPrepared=null,executionApproval=null,executionBinding=null,executionOffset=0,executionTotal=0,executionStudy=null,executionTrials=[],studyApproval=null,executionGraphOffset=0,executionGraphTotal=0,studyTrialOffset=0,studyTrialTotal=0,producerSource=null,producerCurrent=null,producerHealthOffset=0,producerHealthTotal=0;
  let explored=null,exploreOffset=0,exploreTotal=0,historyOffset=0,historyTotal=0;
  const m2DirtyForms=new Set();
  const m2PagedActions=new Set(['data_query','data_history','data_responses','data_response_history',
    'data_preferences','data_preference_history','models','graphs','recipes','studies','runs',
    'lineage','policies','artifacts','materials','selections','searches','producers','source_references','execution_producer_health','files_inspect','file_history','material_intents','material_intent_capabilities','runtime_sources']);
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
  function provenanceOK(value){
    if(exact(value,['method','rights','normalization'])&&value.method==='import'&&str(value.rights,1000)&&value.normalization==='NFC; LF newlines')return true;
    const origin=value?.origin;
    return exact(value,['method','rights','origin'])&&value.method==='project_fork'&&str(value.rights,1000)&&exact(origin,['project_id','checkpoint','family','id','revision','source_revision'])&&id(origin.project_id)&&sha(origin.checkpoint)&&['workbench_text','workbench_record'].includes(origin.family)&&id(origin.id)&&positive(origin.revision)&&positive(origin.source_revision);
  }
  function recordOK(value){
    const fields=['id','kind','name','text','groups','parents','provenance','task','annotation','review','revision','source_revision','created_at','updated_at'];
    return exact(value,fields)&&id(value.id)&&value.kind==='text'&&str(value.name,200)&&str(value.text,200000)&&texts(value.groups,30,1)&&texts(value.parents,30)&&provenanceOK(value.provenance)&&tasks.includes(value.task)&&annotationOK(value.task,value.annotation,true)&&['draft','human_reviewed'].includes(value.review)&&positive(value.revision)&&value.source_revision===1&&str(value.created_at,80)&&str(value.updated_at,80);
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
    m2Controls();m4Controls();runtimeControls();candidateControls();
    if(window.TuldokAuth&&!window.TuldokAuth.canReview())$('record-review').value='draft';
  }
  function showState(){
    if(executionBinding!==state.binding){nativeGraphs=[];nativePrepared=null;nativePending=null;nativeOffset=nativeTotal=0;$('project-native-graph').replaceChildren();$('project-native-phases').replaceChildren();executionBinding=state.binding;executionPrepared=null;executionApproval=null;executionStudy=null;studyApproval=null;executionGraphs=[];executionTrials=[];producerSource=null;producerCurrent=null;$('project-execution-grant').textContent='No current local approval selected.';}
    const root=$('project-files-root'), previous=root.value;root.replaceChildren();
    for(const alias of state.roots){const option=document.createElement('option');option.value=alias;option.textContent=alias;root.append(option);}
    if(state.roots.includes(previous))root.value=previous;
    const destination=$('project-save-as-root'),oldDestination=destination.value;destination.replaceChildren();
    for(const alias of state.roots){const option=document.createElement('option');option.value=alias;option.textContent=alias;destination.append(option);}
    if(state.roots.includes(oldDestination))destination.value=oldDestination;
    const candidateRoot=$('project-candidate-root'),oldCandidateRoot=candidateRoot.value;candidateRoot.replaceChildren();for(const alias of state.roots){const option=document.createElement('option');option.value=alias;option.textContent=alias;candidateRoot.append(option);}if(state.roots.includes(oldCandidateRoot))candidateRoot.value=oldCandidateRoot;
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
    const names=new Set(),chosen=new Set(),versionsChosen=new Map();
    for(const operation of value.operations){
      if(!exact(operation,['id','contracts','availability'])||typeof operation.id!=='string'||!/^[a-z][a-z0-9_.]{0,79}$/.test(operation.id)||names.has(operation.id)||!['available','unavailable','unsupported'].includes(operation.availability)||!Array.isArray(operation.contracts)||!operation.contracts.length||operation.contracts.length>4)throw Error('Unsupported operation capability.');
      names.add(operation.id);const versions=new Set();
      for(const contract of operation.contracts){
        if(!exact(contract,['version','sha256','input_schema','output_schema','scopes','authority','effects','retry','bounds'])||!positive(contract.version)||versions.has(contract.version)||!sha(contract.sha256)||!contract.input_schema||typeof contract.input_schema!=='object'||Array.isArray(contract.input_schema)||!contract.output_schema||typeof contract.output_schema!=='object'||Array.isArray(contract.output_schema)||!texts(contract.scopes,16,0,40)||!['agent','owner'].includes(contract.authority)||!['read','mutation'].includes(contract.effects)||!['read','cas','receipt','never'].includes(contract.retry)||!exact(contract.bounds,['request_bytes','response_bytes','inline_decoded_bytes','json_depth'])||!Object.values(contract.bounds).every(positive))throw Error('Unsupported operation contract.');
        versions.add(contract.version);
        // Remote schemas are opaque discovery data; only installed local pins
        // select behavior. Every request lets the owner verify this exact pin.
        const local=versionPins[operation.id]??(Object.hasOwn(pins,operation.id)?{'1':pins[operation.id]}:{});
        if(operation.availability==='available'&&local[contract.version]===contract.sha256&&contract.version>(versionsChosen.get(operation.id)??0)){chosen.add(operation.id);versionsChosen.set(operation.id,contract.version);}
      }
    }
    selectedContracts=chosen;selectedVersions=versionsChosen;
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
      response=await window.TuldokAuth.fetch(base+path,{method:body===undefined?'GET':'POST',headers:{'Tuldok-Operation-Contract':selectedHeader(operation),...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
      value=await response.json();
    }catch(_){const failure=Error(body===undefined?'Project response unavailable. Refresh status to recover.':'Acknowledgement unavailable; the edit may already be saved. Keep your edits and refresh status before retrying.');failure.code='transport';throw failure;}
    if(ticket!==epoch){message('A superseded project response was ignored. The current view is unchanged.');return null;}
    if(!response.ok){const fields=['error',...(Object.hasOwn(value??{},'code')?['code']:[]),...(Object.hasOwn(value??{},'receipt')?['receipt']:[])];const valid=exact(value,fields)&&str(value.error,1000)&&(!Object.hasOwn(value,'code')||str(value.code,120))&&(!Object.hasOwn(value,'receipt')||receiptOK(value.receipt));const failure=Error(valid?`${value.code??'error'}: ${value.error}`:'Invalid project error response. Refresh status.');failure.code=valid?(value.code??'http_error'):'transport';failure.status=response.status;if(valid&&value.receipt)failure.receipt=value.receipt;throw failure;}
    if(!(kind==='state'?stateOK(value):kind==='fork'?forkOK(value,body):boundOK(value,kind))){const failure=Error('Unsupported project response. The current state is unknown; refresh status before continuing.');failure.code='transport';throw failure;}
    if(kind==='record'&&selectedVersions.get(operation)===1&&[value.record,...value.history].some(record=>record.provenance.method!=='import')){const failure=Error('Version 1 cannot represent retained fork provenance. Refresh contracts.');failure.code='transport';throw failure;}
    if(kind!=='state'&&kind!=='fork'&&(value.binding!==binding||value.project_id!==project||(read&&value.checkpoint!==expected)||(recordId&&value.record?.id!==recordId))){const failure=Error('stale: Response belongs to a different project or checkpoint. Your unsubmitted edits remain here. Refresh status.');failure.code='stale';throw failure;}
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
    if(changed){m4Reset();clearExploration();selected=null;history=[];nextHistory=null;if(!annotationDirty)showRecord();else{$('record-heading').textContent='Unsubmitted annotation from a prior checkpoint';$('record-summary').textContent='Project changed. Your unsubmitted annotation remains below; discard it before selecting a saved record.';$('record-text').value='';}}
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
    state=value;pending=null;if(action!=='save'){m4Reset();clearExploration();selected=null;history=[];nextHistory=null;}showState();if(action!=='save'&&!annotationDirty)showRecord();else if(recovering&&annotationDirty){$('record-heading').textContent='Preserved unsubmitted annotation';$('record-text').value='';}await query(ticket);message(action==='save'?'Project checkpoint is saved.':action==='close'?'Project closed.':`Project ${action==='new'?'created':'opened'}.`);
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
    executionControls();
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
  async function m4Response(action,value,args,project){
    const invalid=()=>{const failure=Error('Saved file or fork response differs from its selected identity, revision or exact bytes.');failure.code='transport';throw failure;};
    const natural=value=>Number.isSafeInteger(value)&&value>=0;
    const safeText=(value,max,empty=false)=>str(value,max,empty)&&!value.includes('\0')&&!Array.from(value).some(ch=>ch.length===1&&ch.charCodeAt(0)>=0xd800&&ch.charCodeAt(0)<=0xdfff);
    const filePath=(kind,path)=>['script','note'].includes(kind)&&safeText(path,512)&&path.startsWith((kind==='script'?'scripts':'notes')+'/')&&!path.includes('\\')&&path.split('/').every(part=>part!==''&&part!=='.'&&part!=='..')&&!/[\x00-\x1f]/.test(path);
    const shaBytes=async raw=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),n=>n.toString(16).padStart(2,'0')).join('');
    const fileID=async value=>shaBytes(new TextEncoder().encode(project+'\0'+value.kind+'\0'+value.path));
    const metadata=value=>exact(value,['revision','sha256','bytes','adopted_at','actor_id'])&&positive(value.revision)&&sha(value.sha256)&&natural(value.bytes)&&value.bytes<=1048576&&safeText(value.adopted_at,80)&&id(value.actor_id);
    const deletedMetadata=value=>exact(value,['revision','deleted','sha256','bytes','adopted_at','actor_id'])&&positive(value.revision)&&value.revision>=2&&value.deleted===true&&value.sha256===null&&value.bytes===0&&safeText(value.adopted_at,80)&&id(value.actor_id);
    const families=['model_definition','pipeline_graph','recipe_definition'];
    const fields=['task','specification','source_selector','preprocessing_policy','output_policy','recipe_source','inputs','runtime','release','nodes','data','evaluation_profile','model','trainer'];
    const reselection=value=>Array.isArray(value)&&value.length<=14&&new Set(value).size===value.length&&value.every(field=>fields.includes(field));
    const origin=value=>exact(value,['project_id','checkpoint','family','id','revision','created_at'])&&id(value.project_id)&&sha(value.checkpoint)&&families.includes(value.family)&&safeText(value.id,512)&&positive(value.revision)&&safeText(value.created_at,80);
    if(['file_get','file_adopt','file_adopt_deletion'].includes(action)){
      const keys=action==='file_get'?['id','project_id','kind','path','version']:['id','project_id','kind','path','revision','sha256','bytes','adopted_at','changed',...(action==='file_adopt_deletion'?['deleted']:[])];
      if(!exact(value,keys)||!sha(value.id)||value.project_id!==project||!filePath(value.kind,value.path)||value.id!==await fileID(value))invalid();
      if(action==='file_get'){
        const v=value.version,deleted=v?.deleted===true,meta=Object.fromEntries(Object.entries(v??{}).filter(([k])=>k!=='text'));
        if(deleted){if(value.kind!=='note'||!exact(v,['revision','deleted','sha256','bytes','adopted_at','actor_id','text'])||!deletedMetadata(meta)||v.text!==null)invalid();}
        else{if(!exact(v,['revision','sha256','bytes','adopted_at','actor_id','text'])||!metadata(meta)||typeof v.text!=='string'||Array.from(v.text).some(ch=>ch.length===1&&ch.charCodeAt(0)>=0xd800&&ch.charCodeAt(0)<=0xdfff))invalid();
          const bytes=new TextEncoder().encode(v.text);if(bytes.length>1048576||bytes.length!==v.bytes||await shaBytes(bytes)!==v.sha256)invalid();}
        if(value.id!==args.file_id||(args.revision!==undefined&&args.revision!==v.revision))invalid();
      }else if(action==='file_adopt_deletion'){
        if(value.kind!=='note'||value.path!==args.path||value.deleted!==true||value.sha256!==null||value.bytes!==0||value.changed!==true||value.revision!==args.expected_revision+1||!safeText(value.adopted_at,80))invalid();
      }else if(value.kind!==args.kind||value.path!==args.path||value.sha256!==args.expected_sha256||!positive(value.revision)||typeof value.changed!=='boolean'||value.revision!==args.expected_revision+Number(value.changed)||!natural(value.bytes)||value.bytes>1048576||!safeText(value.adopted_at,80))invalid();
    }
    if(action==='file_history'&&(!exact(value,['id','items','total','offset','limit'])||value.id!==args.file_id||!value.items.every(item=>metadata(item)||deletedMetadata(item))))invalid();
    if(action==='files_inspect')for(const item of value.items){
      if(!exact(item,['id','kind','path','revision','expected_sha256','expected_bytes','observed_sha256','observed_bytes','state','reason'])||!filePath(item.kind,item.path)||item.id!==await fileID(item)||!positive(item.revision)||!(item.expected_sha256===null||sha(item.expected_sha256))||!natural(item.expected_bytes)||item.expected_bytes>1048576||!(item.observed_sha256===null||sha(item.observed_sha256))||!(item.observed_bytes===null||natural(item.observed_bytes)&&item.observed_bytes<=1048576)||!['unchanged','changed','missing','invalid','deleted'].includes(item.state)||!(item.reason===null||['missing','unsafe_path','too_large','invalid_utf8','unreadable','unstable'].includes(item.reason)))invalid();
      if(item.expected_sha256===null&&(item.kind!=='note'||item.expected_bytes!==0||['unchanged','missing'].includes(item.state)))invalid();
      if(item.state==='deleted'&&(item.expected_sha256!==null||item.observed_sha256!==null||item.observed_bytes!==null||item.reason!==null))invalid();
      if(item.state==='unchanged'&&(item.observed_sha256!==item.expected_sha256||item.observed_bytes!==item.expected_bytes||item.reason!==null))invalid();
    }
    if(action==='material_intents')for(const item of value.items)if(!exact(item,['family','id','catalog_id','definition_id','name','revision','required_reselection','fork_origin'])||!families.includes(item.family)||item.catalog_id!==project||!id(item.definition_id)||item.id!==project+'.'+item.definition_id||!safeText(item.name,200)||item.revision!==1||!reselection(item.required_reselection)||!origin(item.fork_origin)||item.fork_origin.family!==item.family)invalid();
    if(action==='material_intent'){
      const current=value.current;
      if(!exact(value,['family','id','current','fork_origin'])||value.family!==args.family||value.id!==project+'.'+args.definition_id||!exact(current,['format','catalog_id','id','revision','name','definition_family','definition','required_reselection'])||current.format!=='project_material_fork_intent_v1'||current.catalog_id!==project||current.id!==args.definition_id||current.revision!==1||!safeText(current.name,200)||current.definition_family!==args.family||current.definition===null||typeof current.definition!=='object'||Array.isArray(current.definition)||!reselection(current.required_reselection)||!origin(value.fork_origin)||value.fork_origin.family!==args.family)invalid();
    }
    if(action==='material_intent_capabilities')for(const item of value.items)if(!exact(item,['family','id','requires_reselection'])||!families.includes(item.family)||typeof item.id!=='string'||!item.id.startsWith(project+'.')||!id(item.id.slice(33))||!reselection(item.requires_reselection))invalid();
    if(action==='fork_info'){
      const page=value.mapping,offset=args.offset??0,limit=args.limit??40;
      if(!exact(value,['source','project_id','mapping','archived_count','copied_count','missing_regenerable_count'])||value.project_id!==project||!(value.source===null||exact(value.source,['project_id','checkpoint'])&&id(value.source.project_id)&&sha(value.source.checkpoint))||!['archived_count','copied_count','missing_regenerable_count'].every(k=>natural(value[k]))||!exact(page,['items','total','offset','limit'])||!natural(page.total)||page.offset!==offset||page.limit!==limit||!Array.isArray(page.items)||page.items.length!==Math.min(limit,Math.max(0,page.total-offset)))invalid();
      for(const item of page.items)if(!exact(item,['family','source_id','source_revision','destination_id'])||!safeText(item.family,80)||!safeText(item.source_id,512)||!(item.source_revision===null||positive(item.source_revision))||!safeText(item.destination_id,512))invalid();
    }
  }
  async function m2Request(action,arguments_,ticket){
    const operation='project_files.'+action,definition=m2Operations[operation];
    if(!definition||!selectedContracts.has(operation))throw Error('This operation is unavailable for the selected project.');
    const binding=state.binding,cp=checkpoint(),project=state.project.project_id;
    let values={binding,[definition.mutation?'expected_checkpoint':'checkpoint']:cp,...arguments_};
    let path=definition.path;
    for(const [name,value] of Object.entries(values))path=path.replace('{'+name+'}',encodeURIComponent(value));
    const remaining=Object.fromEntries(Object.entries(values).filter(([name])=>!definition.path.includes('{'+name+'}')));
    const options={method:definition.method,cache:'no-store',headers:{'Tuldok-Operation-Contract':selectedHeader(operation)}};
    if(definition.method==='GET')path+='?'+new URLSearchParams(remaining);
    else{
      if(definition.mutation&&!['execution_reconcile_current','execution_study_reconcile_preparation','native_reconcile'].includes(action)){
        let prepared;
        if(action==='runtime_capture'){
          const signature=JSON.stringify(arguments_);
          if(runtimePending&&(runtimePending.signature!==signature||runtimePending.body.binding!==binding))throw Error('Inspect the pending runtime capture outcome, then keep its exact request or explicitly discard the capture form before changing source, inventory or reserve.');
          if(!runtimePending)runtimePending={signature,body:mutationBody(path,arguments_)};
          prepared=runtimePending.body;$('project-runtime-status-key').value=prepared.request_key;$('project-runtime-abandon-key').value=prepared.request_key;
          $('project-runtime-pending').textContent=`Pending capture ${prepared.request_key}: source ${prepared.source}, inventory ${prepared.expected_inventory_sha256}, reserve ${prepared.reserve_bytes??6442450944} bytes. Retry uses these exact fields. Preserve the key until its retained outcome is known.`;
          Object.assign(remaining,prepared);
        }else if(['native_preflight','native_submit','native_retry'].includes(action)){
          const signature=JSON.stringify({action,arguments_});
          if(nativePending&&(nativePending.signature!==signature||nativePending.body.binding!==binding))throw Error('Keep the exact pending native request until its outcome is known, or explicitly discard unsubmitted fields before choosing a different action.');
          if(!nativePending)nativePending={action,signature,body:mutationBody(path,arguments_)};
          prepared=nativePending.body;Object.assign(remaining,Object.fromEntries(Object.entries(prepared).filter(([field])=>!definition.path.includes('{'+field+'}'))));
          $('project-native-pending').textContent=`Pending ${action}: request ${prepared.request_key}. Keep this exact key and fields after a lost acknowledgement. No automatic retry is performed.`;
        }else prepared=mutationBody(path,arguments_);
        values={...values,...prepared};remaining.request_key=prepared.request_key;
      }
      if(['execution_study_prepare_package','execution_study_prepare_verifier'].includes(action)){$('project-candidate-recovery-study').value=arguments_.study_id;$('project-candidate-recovery-key').value=values.request_key;$('project-candidate-preparation-status').textContent=`Pending preparation ${values.request_key}. Preserve this key until its outcome is known.`;}
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
    if(['files_inspect','file_get','file_history','file_adopt','file_adopt_deletion','material_intents','material_intent','material_intent_capabilities','fork_info'].includes(action)){await m4Response(action,value.value,arguments_,project);if(ticket!==epoch)return null;}
    if(action.startsWith('execution_')){
      const result=value.value,invalid=()=>{const failure=Error('Current execution response differs from the selected project, material or action.');failure.code='transport';throw failure;};
      if(Object.hasOwn(result,'origin_catalog_id')&&result.origin_catalog_id!==project)invalid();
      if(['execution_approve_external','execution_study_approve'].includes(action)){
        const grant=result.grant,expected=arguments_.expected_digest??arguments_.expected_material_sha256;
        if(result.format!=='project_current_execution_approval_v1'||result.current_local!==true||!id(grant?.id)||grant.catalog_id!==project||grant.consumer_actor_id!==arguments_.consumer_actor_id||grant.material_sha256!==expected||grant.revoked_at!==null||!Number.isSafeInteger(grant.created_at)||!Number.isSafeInteger(grant.expires_at)||grant.expires_at<=grant.created_at)invalid();
      }
      if(action==='execution_cancel'&&result.run_id!==arguments_.run_id)invalid();
      if(['execution_study_admit','execution_study_stop'].includes(action)&&result.study_id!==arguments_.study_id)invalid();
      if(action==='execution_study_admit'&&(result.trial_id!==arguments_.trial_id||result.reservation?.trial_id!==result.trial_id||result.reservation?.run_id!==result.run_id))invalid();
      const actions={execution_producer_start:'start',execution_generation_resume:'resume',execution_grounded_review:'review',execution_producer_decide:'decide',execution_producer_cancel:'cancel'};
      if(Object.hasOwn(actions,action)){
        const family=arguments_.family??(action==='execution_generation_resume'?'generation_history':'grounded_history');
        if(result.format!=='project_producer_action_v1'||result.family!==family||result.action!==actions[action]||!id(result.producer_id)||(arguments_.producer_id&&result.producer_id!==arguments_.producer_id)||(arguments_.document?.request_id&&result.producer_id!==arguments_.document.request_id))invalid();
      }
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
  function executionControls(){
    const prepared=!!executionPrepared&&executionPrepared.binding===state?.binding,approved=!!executionApproval&&executionApproval.binding===state?.binding;
    producerControls();nativeControls();
    $('project-execution-reconcile').disabled=busy||blocked||!state?.project||!['open','recovery_required'].includes(state.state)||!selectedContracts.has('project_files.execution_reconcile_current');
    $('project-execution-graphs-more').disabled=!m2Allowed('graphs');$('project-execution-graphs-more').hidden=executionGraphOffset>=executionGraphTotal;
    $('project-study-trials-more').disabled=!executionStudy||!m2Allowed('study');$('project-study-trials-more').hidden=studyTrialOffset>=studyTrialTotal;
    $('project-execution-health').disabled=!preparationRecoveryAllowed('execution_health');
    $('project-execution-health-more').disabled=!preparationRecoveryAllowed('execution_health');$('project-execution-health-more').hidden=executionOffset>=executionTotal;
    $('project-execution-graphs').disabled=!m2Allowed('graphs');
    $('project-execution-preflight-fields').disabled=!executionGraphs.length||!m2Allowed('execution_preflight_external');
    $('project-execution-approval-fields').disabled=!prepared||!m2Allowed('execution_approve_external');
    $('project-execution-submit-fields').disabled=!prepared||!approved||!m2Allowed('execution_submit_external');
    $('project-execution-cancel-fields').disabled=!m2Allowed('execution_cancel');
    $('project-study-execution-load').disabled=explored?.category!=='studies'||!m2Allowed('study');
    $('project-study-continue-fields').disabled=!executionStudy||!m2Allowed('execution_study_continue');
    $('project-study-approval-fields').disabled=!executionStudy||!executionTrials.length||!m2Allowed('execution_study_approve');
    $('project-study-admit-fields').disabled=!executionStudy||!studyApproval||!m2Allowed('execution_study_admit');
    $('project-study-stop-fields').disabled=!executionStudy||!m2Allowed('execution_study_stop');
  }
  function executionFact(value){$('project-execution-facts').replaceChildren(projectValue(value));}
  function nativePhaseOK(value,phaseId=null){
    return exact(value,['format','origin_catalog_id','phase_id','phase','run_id','state','spec_sha256','receipt_sha256'])&&value.format==='project_native_phase_v1'&&value.origin_catalog_id===state.project.project_id&&id(value.phase_id)&&(!phaseId||value.phase_id===phaseId)&&['probe','train','verify'].includes(value.phase)&&(value.run_id===null||id(value.run_id))&&['prepared','ready','go_intent','completed','failed','unknown'].includes(value.state)&&sha(value.spec_sha256)&&(value.receipt_sha256===null||sha(value.receipt_sha256));
  }
  function nativeValidationOK(value,revision){
    const fields=['status','valid','errors','validation_token','graph_revision','execution_sha256','release','runtime'];
    if(!value||typeof value!=='object'||Array.isArray(value)||!fields.every(field=>Object.hasOwn(value,field))||!Object.keys(value).every(field=>fields.includes(field)||field==='selection_policy')||!str(value.status,120)||typeof value.valid!=='boolean'||!Array.isArray(value.errors)||value.errors.length>100||!positive(value.graph_revision)||value.graph_revision!==revision||!sha(value.execution_sha256)||!['release','runtime'].every(field=>value[field]===null||typeof value[field]==='object'&&!Array.isArray(value[field])))return false;
    if(!value.errors.every(error=>exact(error,['path','message','code'])&&Object.values(error).every(part=>str(part,2000,true))))return false;
    return value.valid?value.status==='valid'&&value.errors.length===0&&sha(value.validation_token)&&value.release!==null&&value.runtime!==null&&value.runtime.available===true:value.errors.length>0&&value.status===value.errors[0].code&&value.validation_token===null;
  }
  function nativeAdmissionOK(value){return exact(value,['format','origin_catalog_id','run_id','request_sha256'])&&value.format==='project_run_admission_v1'&&value.origin_catalog_id===state.project.project_id&&id(value.run_id)&&sha(value.request_sha256);}
  function nativeControls(){
    $('project-native-graphs').disabled=!m2Allowed('graphs');$('project-native-more').disabled=!m2Allowed('graphs');$('project-native-more').hidden=nativeOffset>=nativeTotal;
    $('project-native-preflight-fields').disabled=!nativeGraphs.length||!m2Allowed('native_preflight');
    $('project-native-submit-fields').disabled=!nativePrepared||nativePrepared.binding!==state?.binding||nativePrepared.checkpoint!==checkpoint()||!m2Allowed('native_submit');
    $('project-native-retry-fields').disabled=!m2Allowed('native_retry');
    $('project-native-reconcile-fields').disabled=!preparationRecoveryAllowed('native_reconcile');
    $('project-native-pending-retry').disabled=!nativePending||nativePending.body.binding!==state?.binding||!preparationRecoveryAllowed(nativePending.action);
  }
  async function loadNativeGraphs(ticket,more=false){
    const value=await m2Request('graphs',{offset:more?nativeOffset:0,limit:40},ticket);if(!value)return;
    if(!more){nativeGraphs=[];nativePrepared=null;$('project-native-graph').replaceChildren();}
    for(const graph of value.items.filter(graph=>graph.recipe!=='external_recipe')){if(!id(graph.id)||!positive(graph.revision))throw Error('Saved native graph has invalid identity.');nativeGraphs.push(graph);const option=document.createElement('option');option.value=graph.id;option.textContent=`${graph.name??graph.id} · ${graph.recipe??'native'} · revision ${graph.revision}`;$('project-native-graph').append(option);}
    nativeOffset=value.offset+value.items.length;nativeTotal=value.total;controls();message('Saved graph metadata loaded. No native probe or Run started.');
  }
  $('project-native-graphs').onclick=()=>run(ticket=>loadNativeGraphs(ticket));$('project-native-more').onclick=()=>run(ticket=>loadNativeGraphs(ticket,true));
  $('project-native-graph').addEventListener('change',()=>{nativePrepared=null;$('project-native-probe-confirm').checked=false;$('project-native-submit-confirm').checked=false;controls();});
  $('project-native-preflight-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const graph=nativeGraphs.find(value=>value.id===$('project-native-graph').value);if(!graph||!$('project-native-probe-confirm').checked)throw Error('Select a saved native graph and explicitly authorize its current CPU probe.');
    nativePrepared=null;controls();
    const value=await m2Request('native_preflight',{graph_id:graph.id,revision:graph.revision},ticket);if(!value)return;
    if(!nativeValidationOK(value,graph.revision))throw Error('Native validation differs from the selected saved graph.');
    nativePending=null;nativePrepared=value.valid?{binding:state.binding,checkpoint:checkpoint(),graph_id:graph.id,revision:graph.revision,validation_token:value.validation_token}:null;
    executionFormSaved('project-native-preflight-form');$('project-native-probe-confirm').checked=false;$('project-native-submit-confirm').checked=false;$('project-native-facts').replaceChildren(projectValue(value));$('project-native-pending').textContent='Native validation acknowledgement saved.';controls();message(value.valid?'Native validation succeeded. Starting a Run requires a separate explicit action.':'Native validation reported errors. No Run was started.');
  });};
  $('project-native-submit-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(!nativePrepared||nativePrepared.binding!==state.binding||nativePrepared.checkpoint!==checkpoint()||!$('project-native-submit-confirm').checked)throw Error('Validate this current graph and separately authorize starting its Run.');
    const value=await m2Request('native_submit',{graph_id:nativePrepared.graph_id,graph_revision:nativePrepared.revision,validation_token:nativePrepared.validation_token},ticket);if(!value)return;if(!nativeAdmissionOK(value))throw Error('Native admission differs from the selected project.');
    nativePending=null;nativePrepared=null;$('project-native-run-id').value=value.run_id;$('project-execution-run-id').value=value.run_id;$('project-native-submit-confirm').checked=false;executionFormSaved('project-native-submit-form');$('project-native-facts').replaceChildren(projectValue(value));$('project-native-pending').textContent='Native admission acknowledged. Refresh current custody to inspect execution.';controls();message($('project-native-pending').textContent);
  });};
  $('project-native-retry-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const run_id=$('project-native-run-id').value;if(!id(run_id)||!$('project-native-retry-confirm').checked)throw Error('Enter a current native Run ID and explicitly authorize a new attempt.');
    const value=await m2Request('native_retry',{run_id},ticket);if(!value)return;if(!nativeAdmissionOK(value)||value.run_id===run_id)throw Error('Native retry admission differs from the selected project.');
    nativePending=null;$('project-native-run-id').value=value.run_id;$('project-execution-run-id').value=value.run_id;$('project-native-retry-confirm').checked=false;executionFormSaved('project-native-retry-form');$('project-native-facts').replaceChildren(projectValue(value));$('project-native-pending').textContent='Native retry admission acknowledged. A saved admission is not proof of completion.';controls();message($('project-native-pending').textContent);
  });};
  $('project-native-pending-retry').onclick=()=>run(async ticket=>{
    if(!nativePending||nativePending.body.binding!==state.binding)throw Error('This tab has no exact current pending native request.');
    const saved=nativePending,{binding,expected_checkpoint,request_key,...args}=saved.body;if(saved.action==='native_preflight'){nativePrepared=null;controls();}const value=await m2Request(saved.action,args,ticket);if(!value)return;
    if(saved.action==='native_preflight'){
      if(!nativeValidationOK(value,args.revision))throw Error('Native validation differs from the original saved graph.');
      nativePrepared=value.valid?{binding:state.binding,checkpoint:checkpoint(),graph_id:args.graph_id,revision:args.revision,validation_token:value.validation_token}:null;
      executionFormSaved('project-native-preflight-form');$('project-native-probe-confirm').checked=false;
    }else{
      if(!nativeAdmissionOK(value)||saved.action==='native_retry'&&value.run_id===args.run_id)throw Error('Native acknowledgement differs from the selected project.');nativePrepared=null;$('project-native-run-id').value=value.run_id;$('project-execution-run-id').value=value.run_id;
      const kind=saved.action==='native_submit'?'submit':'retry';executionFormSaved('project-native-'+kind+'-form');$('project-native-'+kind+'-confirm').checked=false;
    }
    nativePending=null;$('project-native-facts').replaceChildren(projectValue(value));$('project-native-pending').textContent='Exact pending native request acknowledged. No new request key was created.';controls();message($('project-native-pending').textContent);
  });
  $('project-native-reconcile-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const phase_id=$('project-native-phase-id').value;if(!id(phase_id))throw Error('Enter the original current local phase ID.');
    const value=await m2Request('native_reconcile',{phase_id},ticket);if(!value)return;if(!nativePhaseOK(value,phase_id))throw Error('Native reconciliation differs from the original phase.');
    executionFormSaved('project-native-reconcile-form');$('project-native-facts').replaceChildren(projectValue(value));message('Original current native phase observed. Reconciliation does not start or resume it. Refresh project status before another action.');
  });};
  for(const [form,fields] of [['project-native-preflight-form',['project-native-probe-confirm']],['project-native-submit-form',['project-native-submit-confirm']],['project-native-retry-form',['project-native-run-id','project-native-retry-confirm']],['project-native-reconcile-form',['project-native-phase-id']]])for(const field of fields)$(field).addEventListener(field.endsWith('confirm')?'change':'input',()=>{m2DirtyForms.add(form);m2Dirty=true;controls();});
  function localConsumer(){const actor=window.TuldokAuth.identity?.()?.actor_id;return id(actor)?actor:'';}
  async function currentHealth(ticket,more=false){
    const value=await m2Request('execution_health',{offset:more?executionOffset:0,limit:40},ticket);if(!value)return;
    if(value.format!=='project_execution_health_v1'||!Array.isArray(value.active_run_ids)||typeof value.drain_required!=='boolean'||value.offset!==(more?executionOffset:0)||value.limit!==40||value.active_run_ids.length!==Math.min(40,Math.max(0,value.active_count-value.offset)))throw Error('Unsupported current custody observation.');
    let nativeTotal=0;
    if(selectedVersions.get('project_files.execution_health')>=2){
      const page=value.native_phases,ids=page?.items?.map(item=>item.phase_id);
      if(!page||!exact(page,['items','total','offset','limit'])||!Array.isArray(page.items)||!Number.isSafeInteger(page.total)||page.total<0||page.offset!==(more?executionOffset:0)||page.limit!==40||page.items.length!==Math.min(40,Math.max(0,page.total-page.offset))||!page.items.every(item=>nativePhaseOK(item))||ids.join()!==[...new Set(ids)].sort().join())throw Error('Current native phases differ from the selected project or continuation.');
      nativeTotal=page.total;if(!more)$('project-native-phases').replaceChildren();
      for(const phase of page.items){const li=document.createElement('li'),button=document.createElement('button');button.type='button';button.textContent=`${phase.phase_id} · ${phase.phase} · ${phase.state}`;button.onclick=()=>{$('project-native-phase-id').value=phase.phase_id;$('project-native-phase-id').focus();};li.append(button);$('project-native-phases').append(li);}
    }else if(Object.hasOwn(value,'native_phases'))throw Error('Version 1 cannot represent native phase custody. Refresh contracts.');
    executionOffset=(more?executionOffset:0)+40;executionTotal=Math.max(value.active_count,nativeTotal);executionFact(value);
    $('project-execution-summary').textContent=`${value.active_count} current active or unresolved Runs; ${nativeTotal} original current native phases. Local owner ${value.local_owner_active?'active':'inactive'}. ${value.drain_required?'Explicit reconciliation must drain current custody before closing or extracting.':value.available?'The project projection is available.':'The current outcome needs explicit reconciliation.'}`;
    if(value.active_run_ids.length)$('project-execution-run-id').value=value.active_run_ids[0];controls();
  }
  $('project-execution-health').onclick=()=>run(ticket=>currentHealth(ticket));
  $('project-execution-health-more').onclick=()=>run(ticket=>currentHealth(ticket,true));
  $('project-execution-reconcile').onclick=()=>run(async ticket=>{const value=await m2Request('execution_reconcile_current',{},ticket);if(!value)return;executionApproval=null;studyApproval=null;executionFact(value);controls();message(value.available?'Current local custody reconciled and drained. No imported admission was started.':'Current reconciliation remains unavailable; custody is still fenced.');});
  async function loadExecutionGraphs(ticket,more=false){
    const value=await m2Request('graphs',{offset:more?executionGraphOffset:0,limit:40},ticket);if(!value)return;
    if(!more){executionGraphs=[];$('project-execution-graph').replaceChildren();}const graphs=value.items.filter(graph=>graph.recipe==='external_recipe');executionGraphs.push(...graphs);executionGraphOffset=value.offset+value.items.length;executionGraphTotal=value.total;executionPrepared=null;executionApproval=null;
    for(const graph of graphs){const option=document.createElement('option');option.value=graph.id;option.textContent=`${graph.name} · revision ${graph.revision}`;$('project-execution-graph').append(option);}
    $('project-execution-consumer').value=localConsumer();$('project-study-consumer').value=localConsumer();controls();message(executionGraphs.length?'Select an external graph and inspect its exact current material.':'No external graphs on this page. Create one through the named external graph operation.');
  }
  $('project-execution-graphs').onclick=()=>run(ticket=>loadExecutionGraphs(ticket),{clean:true});
  $('project-execution-graphs-more').onclick=()=>run(ticket=>loadExecutionGraphs(ticket,true),{clean:true});
  $('project-execution-graph').addEventListener('change',()=>{executionPrepared=null;executionApproval=null;$('project-execution-grant').textContent='No current local approval selected.';controls();});
  $('project-execution-preflight-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const graph=executionGraphs.find(value=>value.id===$('project-execution-graph').value);if(!graph)throw Error('Select a saved external graph.');
    const value=await m2Request('execution_preflight_external',{graph_id:graph.id,revision:graph.revision},ticket);if(!value)return;
    if(!sha(value.material_sha256)||value.graph_revision!==graph.revision)throw Error('Current material does not match the selected graph revision.');
    executionPrepared={binding:state.binding,graph_id:graph.id,graph_revision:graph.revision,expected_digest:value.material_sha256};executionApproval=null;$('project-execution-confirm').checked=false;executionFact(value);controls();
    message('Exact current material inspected. Review its sources, inputs and runtime before approving. No Run has been admitted.');
  });};
  $('project-execution-approval-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(!executionPrepared||executionPrepared.binding!==state.binding)throw Error('Inspect the exact current material first.');
    if(!$('project-execution-confirm').checked)throw Error('Explicitly approve the reviewed material before granting permission.');
    const consumer=$('project-execution-consumer').value,ttl=Number($('project-execution-ttl').value);if(!id(consumer)||!Number.isInteger(ttl)||ttl<60||ttl>3600)throw Error('Choose the current execution actor and an approval lifetime of 60–3600 seconds.');
    const {binding,...prepared}=executionPrepared,value=await m2Request('execution_approve_external',{...prepared,consumer_actor_id:consumer,ttl_seconds:ttl},ticket);if(!value)return;
    if(value.format!=='project_current_execution_approval_v1'||value.current_local!==true||value.grant?.material_sha256!==prepared.expected_digest||value.grant.consumer_actor_id!==consumer||!id(value.grant.id))throw Error('Current local approval does not match the reviewed request.');
    executionFormSaved('project-execution-approval-form');executionApproval={binding:state.binding,grant:value.grant};$('project-execution-grant').textContent=`Current local approval ${value.grant.id} for actor ${consumer}, expires ${new Date(value.grant.expires_at*1000).toLocaleString()}.`;
    controls();message('Current local approval granted. Starting the Run is a separate explicit action.');
  });};
  $('project-execution-submit-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(executionPrepared?.binding!==state.binding||executionApproval?.binding!==state.binding)throw Error('Review and approve the current material on this installation first.');
    const {binding,...prepared}=executionPrepared,value=await m2Request('execution_submit_external',{...prepared,approval_id:executionApproval.grant.id},ticket);if(!value)return;
    $('project-execution-run-id').value=value.run_id;executionApproval=null;executionFact(value);controls();message(`Admission saved for Run ${value.run_id}. This acknowledges durable intent; refresh current custody to inspect execution.`);
  });};
  $('project-execution-cancel-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const run_id=$('project-execution-run-id').value;if(!id(run_id))throw Error('Choose a current local Run ID.');
    const value=await m2Request('execution_cancel',{run_id},ticket);if(!value)return;executionFact(value);message('Cancellation intent saved. Refresh current custody to establish whether execution has ceased.');
  });};
  $('project-study-execution-load').onclick=()=>run(async ticket=>{
    if(explored?.category!=='studies'||explored.origin!==state.project.project_id)throw Error('Select a current-namespace Study in the scientific history view.');
    const value=await m2Request('study',{study_id:explored.id,origin_catalog_id:explored.origin,offset:0,limit:40},ticket);if(!value)return;
    executionStudy=value.study;studyApproval=null;executionTrials=value.trials.items;studyTrialOffset=value.trials.offset+value.trials.items.length;studyTrialTotal=value.trials.total;$('project-study-execution-trial').replaceChildren();
    for(const trial of executionTrials){const option=document.createElement('option');option.value=trial.id;option.textContent=trial.id;$('project-study-execution-trial').append(option);}
    $('project-study-consumer').value=localConsumer();$('project-study-execution-summary').textContent=`${executionStudy.name} · revision ${executionStudy.revision} · epoch ${executionStudy.admission_epoch} · ${executionStudy.state}. ${value.trials.total} prepared Trials.`;controls();
  },{clean:true});
  $('project-study-trials-more').onclick=()=>run(async ticket=>{const value=await m2Request('study',{study_id:executionStudy.id,origin_catalog_id:state.project.project_id,revision:executionStudy.revision,offset:studyTrialOffset,limit:40},ticket);if(!value)return;for(const trial of value.trials.items){executionTrials.push(trial);const option=document.createElement('option');option.value=trial.id;option.textContent=trial.id;$('project-study-execution-trial').append(option);}studyTrialOffset=value.trials.offset+value.trials.items.length;studyTrialTotal=value.trials.total;controls();});
  $('project-study-execution-trial').addEventListener('change',()=>{studyApproval=null;controls();});
  $('project-study-continue-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const value=await m2Request('execution_study_continue',{study_id:executionStudy.id,revision:executionStudy.revision,admission_epoch:executionStudy.admission_epoch},ticket);if(!value)return;executionStudy=value;controls();$('project-study-execution-summary').textContent=`Current epoch ${value.admission_epoch} · revision ${value.revision} · ${value.state}.`;message('Current Study epoch saved. No Trial has been admitted by this action.');
  });};
  $('project-study-approval-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const trial_id=$('project-study-execution-trial').value,consumer_actor_id=$('project-study-consumer').value;if(!id(trial_id)||!id(consumer_actor_id))throw Error('Select a prepared Trial and current execution actor.');
    const trial=await m2Request('trial',{trial_id,origin_catalog_id:state.project.project_id},ticket);if(!trial)return;
    const value=await m2Request('execution_study_approve',{study_id:executionStudy.id,trial_id,expected_material_sha256:trial.material.sha256,consumer_actor_id},ticket);if(!value)return;executionFormSaved('project-study-approval-form');studyApproval={binding:state.binding,trial_id,grant:value.grant};executionFact(value);controls();message('Exact Trial material approved locally. Admission is a separate explicit action.');
  });};
  $('project-study-admit-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(studyApproval?.binding!==state.binding||studyApproval.trial_id!==$('project-study-execution-trial').value)throw Error('Approve this exact Trial under current local authority first.');
    const value=await m2Request('execution_study_admit',{study_id:executionStudy.id,revision:executionStudy.revision,admission_epoch:executionStudy.admission_epoch,trial_id:studyApproval.trial_id,approval_id:studyApproval.grant.id},ticket);if(!value)return;
    $('project-execution-run-id').value=value.run_id;studyApproval=null;executionStudy=null;executionFact(value);controls();message('Trial admission and budget reservation saved. Reload the Study before another epoch action; refresh current custody for execution status.');
  });};
  $('project-study-stop-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const value=await m2Request('execution_study_stop',{study_id:executionStudy.id,revision:executionStudy.revision},ticket);if(!value)return;executionStudy=null;studyApproval=null;executionFact(value);controls();message('Finite Study epoch closure saved and cancellation requested. Current child custody must still prove cessation.');
  });};
    function producerControls(){
    const family=$('project-producer-task').value,current=!!producerCurrent&&producerCurrent.binding===state?.binding;
    $('project-producer-health').disabled=!m2Allowed('execution_producer_health');$('project-producer-health-more').disabled=!m2Allowed('execution_producer_health');$('project-producer-health-more').hidden=producerHealthOffset>=producerHealthTotal;
    $('project-producer-start-fields').disabled=!m2Allowed('execution_producer_start');
    $('project-producer-source-load').disabled=explored?.category!=='data_query'||!m2Allowed('data_get');
    $('project-producer-current-load').disabled=explored?.category!=='producers'||explored.origin!==state?.project?.project_id||!m2Allowed('producer');
    $('project-producer-label-fields').hidden=family!=='text_proposal_history';
    $('project-producer-count-fields').hidden=!['generation_history','grounded_history'].includes(family);
    $('project-producer-generation-fields').hidden=family!=='generation_history';
    $('project-producer-resume-fields').disabled=!current||producerCurrent.family!=='generation_history'||!m2Allowed('execution_generation_resume');
    $('project-producer-review-fields').disabled=!current||producerCurrent.family!=='grounded_history'||!m2Allowed('execution_grounded_review');
    $('project-producer-decision-fields').disabled=!current||!['caption_proposal_history','text_proposal_history'].includes(producerCurrent.family)||!m2Allowed('execution_producer_decide');
    $('project-producer-cancel-fields').disabled=!current||!m2Allowed('execution_producer_cancel');
  }
  async function producerHealth(ticket,more=false){const value=await m2Request('execution_producer_health',{offset:more?producerHealthOffset:0,limit:40},ticket);if(!value)return;producerHealthOffset=value.offset+value.items.length;producerHealthTotal=value.total;executionFact(value);$('project-producer-health-summary').textContent=`${value.total} current local producer admissions. ${value.fenced?'Current custody is fenced.':'Inspect each current worker and provider outcome before closing.'}`;controls();}
  $('project-producer-health').onclick=()=>run(ticket=>producerHealth(ticket));
  $('project-producer-health-more').onclick=()=>run(ticket=>producerHealth(ticket,true));
  function executionFormSaved(form){m2DirtyForms.delete(form);m2Dirty=m2DirtyForms.size>0;}
  $('project-producer-task').addEventListener('change',()=>{producerSource=null;$('project-producer-source-summary').textContent='Select matching saved data as source.';controls();});
  $('project-producer-source-load').onclick=()=>run(async ticket=>{
    if(explored?.category!=='data_query')throw Error('Select saved data in the scientific history view.');
    const value=await m2Request('data_get',{record_id:explored.id},ticket);if(!value)return;
    const family=$('project-producer-task').value,kind=family==='caption_proposal_history'?'image':'text';
    if(family==='generation_history'||value.kind!==kind)throw Error(`This task requires selected ${kind} data.`);
    producerSource={binding:state.binding,source_id:value.id,revision:value.revision,source_revision:value.source_revision};$('project-producer-source-summary').textContent=`${value.name} · revision ${value.revision} · source revision ${value.source_revision}`;controls();
  });
  $('project-producer-start-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const family=$('project-producer-task').value;if(!$('project-producer-confirm').checked)throw Error('Explicitly authorize this model request.');
    const instruction=$('project-producer-instruction').value,seed=Number($('project-producer-seed').value);
    if(!Number.isInteger(seed)||seed<0||seed>4294967295)throw Error('Use a nonnegative 32-bit seed.');
    const document={server_url:$('project-producer-url').value,model:$('project-producer-model').value,seed};
    if($('project-producer-transport').value==='typed'){document.protocol='pumas_typed_v1';document.profile=$('project-producer-profile').value||null;if(family!=='generation_history')document.seed=null;}
    if(family==='generation_history'){
      Object.assign(document,{prompt:instruction,count:Number($('project-producer-count').value),strategy:$('project-producer-strategy').value,session_id:$('project-producer-session').value,width:Number($('project-producer-width').value),height:Number($('project-producer-height').value)});
      if(document.strategy==='varied'){document.prompt_url=$('project-producer-prompt-url').value;document.prompt_model=$('project-producer-prompt-model').value;}
    }else{
      if(producerSource?.binding!==state.binding)throw Error('Load exact saved source revisions for this project first.');
      const {binding,...source}=producerSource;Object.assign(document,source,{instruction});
      if(family==='grounded_history')document.count=Number($('project-producer-count').value);else document.request_id=key();
      if(family==='text_proposal_history')document.labels=$('project-producer-labels').value.split('\n').filter(value=>value!=='');
    }
    const value=await m2Request('execution_producer_start',{family,document},ticket);if(!value)return;
    executionFormSaved('project-producer-start-form');$('project-producer-confirm').checked=false;producerCurrent=null;executionFact(value);controls();message(`Producer admission saved: ${value.producer_id}. Read its saved history for captured results and current observations.`);
  });};
  $('project-producer-current-load').onclick=()=>run(async ticket=>{
    if(explored?.category!=='producers'||explored.origin!==state.project.project_id)throw Error('Select current-namespace producer history first.');
    const family=explored.value.family,value=await m2Request('producer',{family,producer_id:explored.id,origin_catalog_id:explored.origin,entries_offset:0,entries_limit:40},ticket);if(!value)return;
    producerCurrent={binding:state.binding,family,producer_id:explored.id,job:value.job};$('project-producer-current-summary').textContent=`${family.replaceAll('_',' ')} · ${explored.id} · ${value.status}. Retained history alone does not grant current authority.`;
    $('project-producer-candidate').replaceChildren();for(const candidate of value.job.candidates??[]){const option=document.createElement('option');option.value=candidate.id;option.textContent=`${candidate.text} · ${candidate.status}`;$('project-producer-candidate').append(option);}controls();
  },{clean:true});
  async function producerAction(ticket,action,document){
    if(producerCurrent?.binding!==state.binding)throw Error('Load a current-namespace producer first.');
    const {family,producer_id}=producerCurrent,args={producer_id};if(!['execution_generation_resume','execution_grounded_review'].includes(action))args.family=family;if(document)args.document=document;
    const value=await m2Request(action,args,ticket);if(!value)return;
    for(const form of ['project-producer-review-form','project-producer-decision-form'])executionFormSaved(form);
    producerCurrent=null;executionFact(value);controls();message(action==='execution_producer_cancel'?'Cancellation intent saved. Refresh current producer custody; a retained acknowledgement does not prove cessation.':'Scientific producer action saved. Reload its history before another action.');
  }
  $('project-producer-resume-form').onsubmit=event=>{event.preventDefault();run(ticket=>producerAction(ticket,'execution_generation_resume'));};
  $('project-producer-cancel-form').onsubmit=event=>{event.preventDefault();run(ticket=>producerAction(ticket,'execution_producer_cancel'));};
  $('project-producer-decision-form').onsubmit=event=>{event.preventDefault();run(ticket=>{
    const document={revision:producerCurrent.job.revision,decision:$('project-producer-decision').value};if(producerCurrent.family==='text_proposal_history'&&document.decision==='apply_draft')document.labels=producerCurrent.job.config.labels;return producerAction(ticket,'execution_producer_decide',document);
  });};
  $('project-producer-review-form').onsubmit=event=>{event.preventDefault();run(ticket=>producerAction(ticket,'execution_grounded_review',{revision:producerCurrent.job.revision,candidate_id:$('project-producer-candidate').value,decision:$('project-producer-review-decision').value,note:$('project-producer-note').value}));};

  const preparationRecoveryAllowed=action=>!busy&&!!state?.project&&['open','recovery_required'].includes(state.state)&&selectedContracts.has('project_files.'+action);
  function candidateControls(){
    const kind=$('project-candidate-kind').value||'package';$('project-candidate-verifier-fields').hidden=kind!=='verifier';
    $('project-candidate-prepare-fields').disabled=!m2Allowed('execution_study_prepare_'+kind);
    const reconcile=preparationRecoveryAllowed('execution_study_reconcile_preparation'),abandon=preparationRecoveryAllowed('execution_study_abandon_preparation');
    $('project-candidate-recovery-fields').disabled=!(reconcile||abandon);$('project-candidate-reconcile').disabled=!reconcile;$('project-candidate-abandon').disabled=!abandon;
  }
  function candidatePreparedOK(value,study,candidate=null,runtime=null){
    const keys=['state','candidate_id','trial','graph','model','runtime_snapshot_sha256',...(Object.hasOwn(value??{},'package_run_id')?['package_run_id','package_sha256']:[])];
    return exact(value,keys)&&value.state==='prepared'&&id(value.candidate_id)&&(!candidate||value.candidate_id===candidate)&&sha(value.runtime_snapshot_sha256)&&(!runtime||value.runtime_snapshot_sha256===runtime)&&value.trial?.study_id===study&&id(value.trial?.id)&&value.trial.material?.catalog_id===state.project.project_id&&value.model?.catalog_id===state.project.project_id&&id(value.graph?.id)&&positive(value.graph?.revision)&&(!Object.hasOwn(value,'package_run_id')||id(value.package_run_id)&&sha(value.package_sha256));
  }
  $('project-candidate-prepare-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const study_id=$('project-candidate-study').value,candidate_id=$('project-candidate-id').value,revision=Number($('project-candidate-revision').value),runtime_snapshot_sha256=$('project-candidate-runtime').value,root=$('project-candidate-root').value,directory=$('project-candidate-directory').value,kind=$('project-candidate-kind').value;
    if(!id(study_id)||!id(candidate_id)||!positive(revision)||!sha(runtime_snapshot_sha256)||!root||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$/.test(directory)||!['package','verifier'].includes(kind))throw Error('Choose exact current Study/Candidate identities, revision, publication directory and captured runtime digest.');
    const args={study_id,candidate_id,revision,root,directory,runtime_snapshot_sha256};
    if(kind==='verifier'){args.package_run_id=$('project-candidate-package-run').value;args.package_sha256=$('project-candidate-package-sha').value;if(!id(args.package_run_id)||!sha(args.package_sha256))throw Error('Choose the exact completed package Run and SHA256.');}
    const value=await m2Request('execution_study_prepare_'+kind,args,ticket);if(!value)return;
    if(!candidatePreparedOK(value,study_id,candidate_id,runtime_snapshot_sha256)||kind==='verifier'&&(value.package_run_id!==args.package_run_id||value.package_sha256!==args.package_sha256))throw Error('Preparation result differs from its current Study, Candidate or captured runtime.');
    executionFormSaved('project-candidate-prepare-form');$('project-candidate-preparation-result').textContent=JSON.stringify(value,null,2);$('project-candidate-preparation-status').textContent='Preparation acknowledged. This saved Trial still requires current local approval and a separate explicit admission.';message('Candidate preparation saved. No Run was launched.');
  });};
  async function candidateRecover(ticket,abandon){
    const study_id=$('project-candidate-recovery-study').value,preparation_key=$('project-candidate-recovery-key').value;
    if(!id(study_id)||!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(preparation_key))throw Error('Choose the exact current Study and original preparation request key.');
    const action='execution_study_'+(abandon?'abandon':'reconcile')+'_preparation';if(!state?.project||!['open','recovery_required'].includes(state.state)||!selectedContracts.has('project_files.'+action))throw Error('Current preparation recovery is unavailable.');
    const args={study_id,preparation_key};if(abandon){args.reason=$('project-candidate-abandon-reason').value;if(!str(args.reason,1000))throw Error('Enter an explicit reason before abandoning the stopped partial preparation.');}
    const value=await m2Request(action,args,ticket);if(!value)return;
    if(abandon){if(value.format!=='project_candidate_preparation_abandon_v1'||value.state!=='abandoned'||value.origin_catalog_id!==state.project.project_id||value.study_id!==study_id||value.preparation_key!==preparation_key||value.reason!==args.reason||!sha(value.input_sha256)||!sha(value.observed_checkpoint)||value.candidate?.catalog_id!==state.project.project_id)throw Error('Abandonment differs from the exact current preparation intent.');executionFormSaved('project-candidate-recovery-form');}
    else if(!candidatePreparedOK(value,study_id))throw Error('Reconciled preparation belongs to another Study.');
    executionFormSaved('project-candidate-prepare-form');$('project-candidate-preparation-result').textContent=JSON.stringify(value,null,2);$('project-candidate-preparation-status').textContent=abandon?'Stopped partial preparation abandoned; original staging and scientific facts remain. Refresh project status.':'Final preparation acknowledged; no writer was replayed and no Run was launched. Refresh project status.';message($('project-candidate-preparation-status').textContent);
  }
  $('project-candidate-reconcile').onclick=()=>run(ticket=>candidateRecover(ticket,false));$('project-candidate-abandon').onclick=()=>run(ticket=>candidateRecover(ticket,true));
  for(const [form,fields] of [['project-candidate-prepare-form',['project-candidate-study','project-candidate-revision','project-candidate-id','project-candidate-kind','project-candidate-root','project-candidate-directory','project-candidate-runtime','project-candidate-package-run','project-candidate-package-sha']],['project-candidate-recovery-form',['project-candidate-recovery-study','project-candidate-recovery-key','project-candidate-abandon-reason']]])for(const field of fields)$(field).addEventListener(field==='project-candidate-kind'?'change':'input',()=>{m2DirtyForms.add(form);m2Dirty=true;controls();});

  function runtimeSummaryOK(value,complete=false){
    const keys=['format','project_id','manifest_sha256','file_count','total_bytes','actor_id','observed_at','request_key',...(complete?['runtime_ref']:[])];
    return exact(value,keys)&&value.format===(complete?'project_runtime_capture_v1':'project_runtime_capture_intent_v1')&&id(value.project_id)&&sha(value.manifest_sha256)&&positive(value.file_count)&&value.file_count<=40000&&Number.isSafeInteger(value.total_bytes)&&value.total_bytes>=0&&value.total_bytes<=2147483648&&id(value.actor_id)&&str(value.observed_at,80)&&typeof value.request_key==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(value.request_key)&&(!complete||exact(value.runtime_ref,['kind','catalog_id','id','sha256'])&&value.runtime_ref.kind==='runtime'&&value.runtime_ref.catalog_id===value.project_id&&sha(value.runtime_ref.id)&&value.runtime_ref.id===value.runtime_ref.sha256);
  }
  function runtimeControls(){
    $('project-runtime-sources').disabled=!m2Allowed('runtime_sources');$('project-runtime-sources-more').disabled=!m2Allowed('runtime_sources');
    $('project-runtime-inspect').disabled=!$('project-runtime-source').value||!m2Allowed('runtime_inspect');
    $('project-runtime-source').disabled=!m2Allowed('runtime_inspect');
    $('project-runtime-files-more').disabled=!runtimeInspection||runtimeInspection.binding!==state?.binding||!m2Allowed('runtime_inspect');
    $('project-runtime-capture-fields').disabled=!runtimeInspection||runtimeInspection.binding!==state?.binding||!m2Allowed('runtime_capture');
    $('project-runtime-capture').disabled=$('project-runtime-capture-fields').disabled||!$('project-runtime-confirm').checked;
    $('project-runtime-status-fields').disabled=!preparationRecoveryAllowed('runtime_status');
    $('project-runtime-abandon-fields').disabled=!preparationRecoveryAllowed('runtime_abandon');
    $('project-runtime-retry').disabled=!runtimePending||runtimePending.body.binding!==state?.binding||!preparationRecoveryAllowed('runtime_capture');
  }
  async function runtimeSources(ticket,more=false){
    const offset=more?runtimeSourceOffset:0,value=await m2Request('runtime_sources',{offset,limit:40},ticket);if(!value)return;
    if(!value.items.every(item=>exact(item,['source'])&&typeof item.source==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(item.source)))throw Error('Unsupported configured runtime source page.');
    if(!more){$('project-runtime-source').replaceChildren();runtimeInspection=null;$('project-runtime-confirm').checked=false;}
    for(const item of value.items){const option=document.createElement('option');option.value=item.source;option.textContent=item.source;$('project-runtime-source').append(option);}
    runtimeSourceOffset=offset+value.items.length;runtimeSourceTotal=value.total;$('project-runtime-sources-more').hidden=runtimeSourceOffset>=runtimeSourceTotal;controls();
    message(value.total?'Choose a current source and explicitly inspect it. No runtime has been captured.':'No current runtime sources are configured on this installation.');
  }
  async function runtimeInspect(ticket,more=false){
    const source=$('project-runtime-source').value;if(!source)throw Error('Choose a configured source alias.');
    const offset=more?runtimeFileOffset:0,value=await m2Request('runtime_inspect',{source,offset,limit:40},ticket);if(!value)return;
    const page=value.files;
    if(!exact(value,['format','source','inventory_sha256','profile','python_version','file_count','total_bytes','manifest_bytes','free_bytes','packages','launch','files'])||value.format!=='project_runtime_inspection_v1'||value.source!==source||!sha(value.inventory_sha256)||value.profile!=='captured_cpu_python_v1'||value.python_version!=='3.12'||!positive(value.file_count)||value.file_count>40000||!positive(value.total_bytes)||value.total_bytes>2147483648||!positive(value.manifest_bytes)||value.manifest_bytes>16777216||!Number.isSafeInteger(value.free_bytes)||value.free_bytes<0||!Array.isArray(value.packages)||value.packages.length<2||value.packages.length>256||!value.packages.every(item=>exact(item,['name','version'])&&str(item.name,128)&&str(item.version,128))||!exact(page,['items','total','offset','limit'])||page.total!==value.file_count||page.offset!==offset||page.limit!==40||!Array.isArray(page.items)||page.items.length!==Math.min(40,Math.max(0,page.total-offset)))throw Error('Runtime inventory differs from the reviewed source or continuation.');
    if(!page.items.every(item=>exact(item,['path','bytes','sha256','mode','kind'])&&str(item.path,1024)&&Number.isSafeInteger(item.bytes)&&item.bytes>=0&&item.bytes<=536870912&&sha(item.sha256)&&[256,320].includes(item.mode)&&['data','elf'].includes(item.kind)))throw Error('Unsupported runtime file inventory.');
    if(more&&(!runtimeInspection||runtimeInspection.binding!==state.binding||runtimeInspection.source!==source||runtimeInspection.inventory_sha256!==value.inventory_sha256))throw Error('Current runtime inventory changed between pages. Inspect it again before capture.');
    if(!more){runtimeInspection={binding:state.binding,source,inventory_sha256:value.inventory_sha256};$('project-runtime-files').replaceChildren();$('project-runtime-confirm').checked=false;}
    $('project-runtime-summary').textContent=`Current configured source ${source} · ${value.inventory_sha256} · ${value.file_count} files · ${value.total_bytes} bytes · ${value.free_bytes} bytes currently free. This observation does not capture a runtime.`;
    $('project-runtime-layout').textContent=JSON.stringify({python_version:value.python_version,packages:value.packages,launch:value.launch},null,2);
    for(const item of page.items){const li=document.createElement('li');li.textContent=`${item.path} · ${item.kind} · ${item.bytes} bytes · ${item.sha256}`;$('project-runtime-files').append(li);}
    runtimeFileOffset=offset+page.items.length;runtimeFileTotal=page.total;$('project-runtime-files-more').hidden=runtimeFileOffset>=runtimeFileTotal;controls();
  }
  $('project-runtime-sources').onclick=()=>run(ticket=>runtimeSources(ticket));$('project-runtime-sources-more').onclick=()=>run(ticket=>runtimeSources(ticket,true));
  $('project-runtime-inspect').onclick=()=>run(ticket=>runtimeInspect(ticket));$('project-runtime-files-more').onclick=()=>run(ticket=>runtimeInspect(ticket,true));
  $('project-runtime-source').addEventListener('change',()=>{runtimeInspection=null;$('project-runtime-confirm').checked=false;controls();});
  function runtimeAbandonmentOK(value,key,reason=null){
    return exact(value,['format','project_id','capture_key','input_sha256','manifest_sha256','actor_id','reason','observed_checkpoint','observed_at'])&&value.format==='project_runtime_capture_abandon_v1'&&value.project_id===state.project.project_id&&value.capture_key===key&&sha(value.input_sha256)&&sha(value.manifest_sha256)&&id(value.actor_id)&&str(value.reason,1000)&&(reason===null||value.reason===reason)&&sha(value.observed_checkpoint)&&str(value.observed_at,80);
  }
  async function captureRuntime(ticket,retry=false){
    let args;
    if(retry){
      if(!runtimePending||runtimePending.body.binding!==state.binding)throw Error('This tab has no exact current pending capture request. Inspect retained status before choosing a new action.');
      const {binding,expected_checkpoint,request_key,...saved}=runtimePending.body;args=saved;
    }else{
      if(runtimeInspection?.binding!==state.binding||!$('project-runtime-confirm').checked)throw Error('Inspect and explicitly confirm the current source inventory before capture.');
      const reserve_bytes=Number($('project-runtime-reserve').value);if(!Number.isSafeInteger(reserve_bytes)||reserve_bytes<0)throw Error('Choose a nonnegative safe integer disk reserve.');
      args={source:runtimeInspection.source,expected_inventory_sha256:runtimeInspection.inventory_sha256,reserve_bytes};
    }
    const value=await m2Request('runtime_capture',args,ticket);if(!value)return;
    if(!runtimeSummaryOK(value,true)||value.project_id!==state.project.project_id||value.manifest_sha256!==args.expected_inventory_sha256||value.request_key!==runtimePending?.body.request_key)throw Error('Runtime capture acknowledgement differs from the reviewed inventory or pending request.');
    $('project-runtime-status-key').value=value.request_key;runtimePending=null;
    if(Number($('project-runtime-reserve').value)===args.reserve_bytes)executionFormSaved('project-runtime-capture-form');$('project-runtime-confirm').checked=false;
    $('project-runtime-pending').textContent=`Capture request ${value.request_key} acknowledged. Retained capture facts do not grant permission to execute.`;$('project-runtime-status').textContent=JSON.stringify(value,null,2);controls();message('Reviewed runtime bytes captured locally and scientific metadata saved. No project execution started.');
  }
  $('project-runtime-capture-form').onsubmit=event=>{event.preventDefault();run(ticket=>captureRuntime(ticket));};
  $('project-runtime-retry').onclick=()=>run(ticket=>captureRuntime(ticket,true));
  $('project-runtime-abandon-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const capture_key=$('project-runtime-abandon-key').value,reason=$('project-runtime-abandon-reason').value;
    if(!/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(capture_key)||!str(reason,1000))throw Error('Choose the exact current capture key and an explicit abandonment reason.');
    const value=await m2Request('runtime_abandon',{capture_key,reason},ticket);if(!value)return;
    if(!runtimeAbandonmentOK(value,capture_key,reason))throw Error('Runtime abandonment differs from the current exact capture and reason.');
    if(runtimePending?.body.request_key===capture_key){if(Number($('project-runtime-reserve').value)===runtimePending.body.reserve_bytes)executionFormSaved('project-runtime-capture-form');runtimePending=null;}
    executionFormSaved('project-runtime-abandon-form');$('project-runtime-status-key').value=capture_key;$('project-runtime-status').textContent=JSON.stringify(value,null,2);$('project-runtime-pending').textContent='Stopped partial capture abandoned. Original partial bytes and scientific intent remain. Refresh project status.';message($('project-runtime-pending').textContent);controls();
  });};
  $('project-runtime-status-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const capture_key=$('project-runtime-status-key').value;if(!/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(capture_key))throw Error('Choose the exact retained capture request key.');
    const value=await m2Request('runtime_status',{capture_key},ticket);if(!value)return;
    const abandoned=value?.state==='abandoned';
    if(!exact(value,abandoned?['state','intent','result','abandonment']:['state','intent','result'])||!['absent','intent_recorded','captured','abandoned'].includes(value.state)||value.state!==(abandoned?'abandoned':value.result?'captured':value.intent?'intent_recorded':'absent')||value.result&&!value.intent||value.intent!==null&&!runtimeSummaryOK(value.intent)||value.result!==null&&!runtimeSummaryOK(value.result,true)||[value.intent,value.result].some(item=>item!==null&&(item.project_id!==state.project.project_id||item.request_key!==capture_key))||value.result&&['project_id','manifest_sha256','file_count','total_bytes','request_key'].some(field=>value.intent[field]!==value.result[field])||abandoned&&(!value.intent||value.result!==null||!runtimeAbandonmentOK(value.abandonment,capture_key)||value.abandonment.manifest_sha256!==value.intent.manifest_sha256))throw Error('Retained runtime status differs from the selected capture request.');
    $('project-runtime-status').textContent=JSON.stringify(value,null,2);message('Retained capture outcome loaded. Current local readiness was not inspected.');
  });};
  for(const field of ['project-runtime-abandon-key','project-runtime-abandon-reason'])$(field).addEventListener('input',()=>{m2DirtyForms.add('project-runtime-abandon-form');m2Dirty=true;controls();});
  for(const field of ['project-runtime-reserve','project-runtime-confirm'])$(field).addEventListener(field.endsWith('confirm')?'change':'input',()=>{m2DirtyForms.add('project-runtime-capture-form');m2Dirty=true;controls();});

  function m4Controls(){
    $('project-save-as-fields').disabled=!m2Allowed('save_as');
    $('project-working-load').disabled=!m2Allowed('files_inspect');$('project-working-more').disabled=!m2Allowed('files_inspect');
    $('project-working-adopt-fields').disabled=!m2Allowed('file_adopt');
    $('project-working-delete-fields').disabled=!m2Allowed('file_adopt_deletion')||!workingDeletion||workingDeletion.binding!==state?.binding||workingDeletion.checkpoint!==checkpoint();
    $('project-working-history').disabled=!workingSelection||workingSelection.binding!==state?.binding||!m2Allowed('file_history');
    $('project-working-history-more').disabled=!m2Allowed('file_history');
    for(const [button,action] of [['project-fork-load','fork_info'],['project-fork-more','fork_info'],['project-intents-load','material_intents'],['project-intents-more','material_intents'],['project-intent-capabilities','material_intent_capabilities'],['project-intent-capabilities-more','material_intent_capabilities']])$(button).disabled=!m2Allowed(action);
  }
  function m4Reset(){
    runtimeInspection=null;runtimeSourceOffset=runtimeSourceTotal=runtimeFileOffset=runtimeFileTotal=0;$('project-runtime-source').replaceChildren();$('project-runtime-files').replaceChildren();$('project-runtime-layout').textContent='';$('project-runtime-summary').textContent='';$('project-runtime-confirm').checked=false;
    workingSelection=null;clearWorkingDeletion();workingOffset=workingTotal=workingHistoryOffset=workingHistoryTotal=intentsOffset=intentsTotal=forkOffset=forkTotal=intentCapsOffset=intentCapsTotal=0;
    for(const name of ['project-working-list','project-working-history-list','project-fork-list','project-intents-list'])$(name).replaceChildren();
    $('project-working-text').value='';$('project-working-summary').textContent='';$('project-intent-detail').textContent='';
    for(const name of ['project-working-more','project-working-history-more','project-fork-more','project-intents-more','project-intent-capabilities-more'])$(name).hidden=true;
  }
  function forkOK(value,body){
    if(!exact(value,['state','fork'])||!stateOK(value.state)||value.state.state!=='open')return false;
    const f=value.fork;
    return exact(f,['source_project_id','source_checkpoint','project_id','checkpoint','root','directory','request_key','reconciled','mapping_count','copied_count','missing_regenerable_count'])&&
      id(f.source_project_id)&&id(f.project_id)&&f.source_project_id!==f.project_id&&sha(f.source_checkpoint)&&sha(f.checkpoint)&&
      f.source_checkpoint===body.expected_checkpoint&&f.source_project_id===forkPending?.source_project_id&&
      ['root','directory','request_key'].every(field=>f[field]===body[field])&&typeof f.reconciled==='boolean'&&
      ['mapping_count','copied_count','missing_regenerable_count'].every(field=>Number.isSafeInteger(f[field])&&f[field]>=0)&&
      value.state.binding!==body.binding&&value.state.project.project_id===f.project_id&&value.state.project.checkpoint===f.checkpoint&&value.state.project.name===body.name;
  }
  $('project-save-as-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    if(importDirty||annotationDirty||[...m2DirtyForms].some(form=>form!=='project-save-as-form'))throw Error('Submit or discard other unsubmitted edits before Save As.');
    const fields={root:$('project-save-as-root').value,directory:$('project-save-as-directory').value,name:$('project-save-as-name').value.trim()},signature=JSON.stringify(fields);
    if(!fields.root||!fields.directory||!fields.name)throw Error('Choose a new root, relative directory and project name.');
    if(forkPending&&forkPending.signature!==signature)throw Error('Inspect the pending Save As destination, then keep its exact request or explicitly discard this form before choosing another destination.');
    if(!forkPending)forkPending={signature,source_project_id:state.project.project_id,body:mutationBody('/save-as',fields)};
    const result=await request('/save-as',{body:forkPending.body,ticket,kind:'fork'});if(!result)return;
    state=result.state;forkPending=null;pending=null;executionFormSaved('project-save-as-form');m4Reset();clearExploration();selected=null;history=[];nextHistory=null;showRecord();showState();
    const f=result.fork;$('project-save-as-summary').textContent=`Independent project ${f.project_id}; ${f.mapping_count} editable mappings, ${f.copied_count} copied payloads, ${f.missing_regenerable_count} missing regenerable payloads. Source checkpoint ${f.source_checkpoint} is retained as its origin.`;
    await query(ticket);message('Independent project created and selected. Review its fork origins and binding readiness.');return $('project-fork-load');
  });};
  async function inspectWorking(ticket,more=false){
    const offset=more?workingOffset:0,value=await m2Request('files_inspect',{offset,limit:40},ticket);if(!value)return;
    clearWorkingDeletion();if(!more)$('project-working-list').replaceChildren();
    for(const item of value.items){const li=document.createElement('li'),button=document.createElement('button');button.type='button';button.textContent=`${item.path} · ${item.state} · captured revision ${item.revision}`;button.onclick=()=>run(async next=>{
      const version=await m2Request('file_get',{file_id:item.id},next);if(!version)return;showWorking(version);
      if(item.kind==='note'&&item.state==='missing'&&sha(item.expected_sha256)){workingDeletion={binding:state.binding,checkpoint:checkpoint(),path:item.path,revision:item.revision,sha256:item.expected_sha256};$('project-working-delete-summary').textContent=`Missing note ${item.path} · captured revision ${item.revision} · SHA256 ${item.expected_sha256}. Earlier text will remain in revision history.`;}
      controls();$('project-working-kind').value=item.kind;$('project-working-path').value=item.path;$('project-working-revision').value=String(item.revision);$('project-working-sha').value=item.observed_sha256??'';
      message(item.state==='unchanged'?'Captured bytes match the current file.':'Current file differs or is unavailable. Review its exact current digest before adoption.');return $('project-working-heading');
    },{clean:true});li.append(button);$('project-working-list').append(li);}
    workingOffset=offset+value.items.length;workingTotal=value.total;$('project-working-more').hidden=workingOffset>=workingTotal;
  }
  function clearWorkingDeletion(){
    workingDeletion=null;$('project-working-delete-confirm').checked=false;executionFormSaved('project-working-delete-form');
    $('project-working-delete-summary').textContent='Inspect and select a known missing note first. This action records its absence and keeps all captured revisions.';
  }
  function showWorking(value){
    clearWorkingDeletion();
    workingSelection={id:value.id,binding:state.binding};$('project-working-heading').textContent=value.path;
    $('project-working-summary').textContent=value.version.deleted===true?`Captured revision ${value.version.revision} · note deletion retained. No text is present in this revision; select an earlier revision to read its captured text.`:`Captured revision ${value.version.revision} · ${value.version.sha256} · ${value.version.bytes} bytes${value.version.bytes===0?' · empty file':''}.`;
    $('project-working-text').value=value.version.deleted===true?'':value.version.text;controls();
  }
  async function workingHistory(ticket,more=false){
    if(!workingSelection||workingSelection.binding!==state.binding)throw Error('Select a file from the current project first.');
    const offset=more?workingHistoryOffset:0,value=await m2Request('file_history',{file_id:workingSelection.id,offset,limit:40},ticket);if(!value)return;
    if(value.id!==workingSelection.id)throw Error('Working-file history belongs to another file.');
    if(!more)$('project-working-history-list').replaceChildren();
    for(const version of value.items){const li=document.createElement('li'),button=document.createElement('button');button.type='button';button.textContent=`Revision ${version.revision} · ${version.deleted===true?'note deletion':version.sha256} · ${version.adopted_at}`;button.onclick=()=>run(async next=>{const result=await m2Request('file_get',{file_id:workingSelection.id,revision:version.revision},next);if(result)showWorking(result);return $('project-working-heading');});li.append(button);$('project-working-history-list').append(li);}
    workingHistoryOffset=offset+value.items.length;workingHistoryTotal=value.total;$('project-working-history-more').hidden=workingHistoryOffset>=workingHistoryTotal;
  }
  $('project-working-local').addEventListener('change',()=>run(async()=>{
    const file=$('project-working-local').files?.[0];if(!file)return;if(file.size>1048576)throw Error('Choose a UTF-8 file of at most 1 MiB.');
    const bytes=await file.arrayBuffer();new TextDecoder('utf-8',{fatal:true}).decode(bytes);
    $('project-working-sha').value=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),value=>value.toString(16).padStart(2,'0')).join('');
    m2DirtyForms.add('project-working-adopt-form');m2Dirty=true;message('Matching local file digest calculated. Review the server project path and expected adopted revision before adoption.');
  }));
  $('project-working-adopt-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const args={kind:$('project-working-kind').value,path:$('project-working-path').value,expected_revision:Number($('project-working-revision').value),expected_sha256:$('project-working-sha').value};
    const result=await m2Request('file_adopt',args,ticket);if(!result)return;executionFormSaved('project-working-adopt-form');$('project-working-revision').value=String(result.revision);
    await inspectWorking(ticket);const saved=await m2Request('file_get',{file_id:result.id,revision:result.revision},ticket);if(saved)showWorking(saved);message('Exact working-file bytes adopted. The captured text remains inert.');return $('project-working-heading');
  });};
  $('project-working-delete-confirm').addEventListener('change',()=>{m2DirtyForms.add('project-working-delete-form');m2Dirty=true;controls();});
  $('project-working-delete-form').onsubmit=event=>{event.preventDefault();run(async ticket=>{
    const selected=workingDeletion;if(!selected||selected.binding!==state.binding||selected.checkpoint!==checkpoint()||!$('project-working-delete-confirm').checked)throw Error('Inspect and select a known missing note, then explicitly confirm its deletion revision.');
    const result=await m2Request('file_adopt_deletion',{path:selected.path,expected_revision:selected.revision,expected_sha256:selected.sha256},ticket);if(!result)return;
    executionFormSaved('project-working-delete-form');clearWorkingDeletion();await inspectWorking(ticket);
    const saved=await m2Request('file_get',{file_id:result.id,revision:result.revision},ticket);if(saved)showWorking(saved);
    message('Note deletion retained. Earlier captured text remains available in revision history.');return $('project-working-heading');
  });};
  async function forkInfo(ticket,more=false){
    const offset=more?forkOffset:0,value=await m2Request('fork_info',{offset,limit:40},ticket);if(!value)return;
    const page=value.mapping;if(!exact(page,['items','total','offset','limit'])||page.offset!==offset||page.limit!==40||!Array.isArray(page.items)||page.items.length!==Math.min(40,Math.max(0,page.total-offset)))throw Error('Fork mapping continuation differs.');
    if(!more)$('project-fork-list').replaceChildren();$('project-fork-summary').textContent=value.source?`Fork origin ${value.source.project_id} at ${value.source.checkpoint}; ${value.archived_count} archived records, ${value.copied_count} copied payloads, ${value.missing_regenerable_count} missing regenerable payloads.`:'This project has no independent-fork origin overlay.';
    for(const mapping of page.items){const li=document.createElement('li');li.textContent=`${mapping.family}: ${mapping.source_id} revision ${mapping.source_revision??'none'} → ${mapping.destination_id}`;$('project-fork-list').append(li);}
    forkOffset=offset+page.items.length;forkTotal=page.total;$('project-fork-more').hidden=forkOffset>=forkTotal;
  }
  async function intentList(ticket,more=false,capabilities=false){
    const offset=more?(capabilities?intentCapsOffset:intentsOffset):0,action=capabilities?'material_intent_capabilities':'material_intents';
    const value=await m2Request(action,{offset,limit:40},ticket);if(!value)return;if(!more)$('project-intents-list').replaceChildren();
    for(const item of value.items){const li=document.createElement('li'),fields=capabilities?item.requires_reselection:item.required_reselection;
      if(capabilities)li.textContent=`${item.family} · ${item.id} · ${fields.length?'Reselect '+fields.join(', '):'Current editable definition; execution still requires current permission.'}`;
      else{const button=document.createElement('button');button.type='button';button.textContent=`${item.name} · ${item.family} · reselect ${fields.join(', ')}`;button.onclick=()=>run(async next=>{const detail=await m2Request('material_intent',{family:item.family,definition_id:item.definition_id},next);if(!detail)return;$('project-intent-title').textContent=detail.current.name;$('project-intent-detail').textContent=JSON.stringify(detail,null,2);return $('project-intent-title');});li.append(button);}
      $('project-intents-list').append(li);}
    if(capabilities){intentCapsOffset=offset+value.items.length;intentCapsTotal=value.total;$('project-intent-capabilities-more').hidden=intentCapsOffset>=intentCapsTotal;}
    else{intentsOffset=offset+value.items.length;intentsTotal=value.total;$('project-intents-more').hidden=intentsOffset>=intentsTotal;}
  }
  $('project-working-load').onclick=()=>run(ticket=>inspectWorking(ticket),{clean:true});$('project-working-more').onclick=()=>run(ticket=>inspectWorking(ticket,true));
  $('project-working-history').onclick=()=>run(ticket=>workingHistory(ticket));$('project-working-history-more').onclick=()=>run(ticket=>workingHistory(ticket,true));
  $('project-fork-load').onclick=()=>run(ticket=>forkInfo(ticket));$('project-fork-more').onclick=()=>run(ticket=>forkInfo(ticket,true));
  $('project-intents-load').onclick=()=>run(ticket=>intentList(ticket));$('project-intents-more').onclick=()=>run(ticket=>intentList(ticket,true));
  $('project-intent-capabilities').onclick=()=>run(ticket=>intentList(ticket,false,true));$('project-intent-capabilities-more').onclick=()=>run(ticket=>intentList(ticket,true,true));
  for(const [form,fields] of [['project-save-as-form',['project-save-as-directory','project-save-as-name','project-save-as-root']],['project-working-adopt-form',['project-working-path','project-working-revision','project-working-sha','project-working-kind']]])for(const field of fields)$(field).addEventListener('input',()=>{m2DirtyForms.add(form);m2Dirty=true;controls();});

  for(const [form,fields] of [['project-producer-start-form',['project-producer-url','project-producer-model','project-producer-instruction','project-producer-labels','project-producer-seed','project-producer-profile','project-producer-session','project-producer-width','project-producer-height','project-producer-count','project-producer-prompt-url','project-producer-prompt-model']],['project-producer-review-form',['project-producer-note']],['project-execution-approval-form',['project-execution-consumer','project-execution-ttl']],['project-study-approval-form',['project-study-consumer']]])for(const field of fields)$(field).addEventListener('input',()=>{m2DirtyForms.add(form);m2Dirty=true;controls();});
  for(const action of ['new','open','save','close'])$('project-files-'+action).onclick=()=>lifecycle(action);
  $('project-files-refresh').onclick=refresh;
  $('records-more').onclick=()=>run(async ticket=>{await query(ticket,true);message('More text records loaded.');return nextRecord===null?$('records-title'):$('records-more');});
  $('record-history-more').onclick=olderHistory;
  $('project-files-discard').onclick=()=>{importDirty=false;annotationDirty=false;m2Dirty=false;m2DirtyForms.clear();clearWorkingDeletion();nativePending=null;nativePrepared=null;for(const field of ['project-native-probe-confirm','project-native-submit-confirm','project-native-retry-confirm'])$(field).checked=false;forkPending=null;runtimePending=null;runtimeInspection=null;for(const field of ['project-candidate-study','project-candidate-id','project-candidate-directory','project-candidate-runtime','project-candidate-package-run','project-candidate-package-sha','project-candidate-recovery-study','project-candidate-recovery-key','project-candidate-abandon-reason','project-runtime-abandon-key','project-runtime-abandon-reason'])$(field).value='';$('project-runtime-confirm').checked=false;$('project-runtime-pending').textContent='';for(const field of ['project-save-as-directory','project-save-as-name','project-working-path','project-working-sha','project-working-local'])$(field).value='';$('project-working-revision').value='0';executionApproval=null;studyApproval=null;producerCurrent=null;for(const field of ['project-producer-url','project-producer-model','project-producer-instruction','project-producer-labels','project-producer-note','project-producer-profile','project-producer-session','project-producer-prompt-url','project-producer-prompt-model'])$(field).value='';$('project-producer-confirm').checked=false;$('project-execution-confirm').checked=false;$('project-artifact-path').value='';for(const form of ['project-model-create-form','project-study-create-form','project-register-form','project-scientific-form'])for(const field of $(form).querySelectorAll('input'))field.value=field.defaultValue??'';clearExplorationDetail();$('project-source-file').value='';$('project-source-name').value='';$('project-search-name').value='';$('project-selection-name').value='';$('text-name').value='';$('text-content').value='';$('text-groups').value='project';$('text-rights').value='unknown';showRecord();clearError();message('Unsubmitted edits discarded. Saved project records are unchanged.');};
  for(const field of ['text-name','text-content','text-groups','text-rights'])$(field).addEventListener('input',()=>{importDirty=true;controls();});
  for(const field of ['annotation-value','annotation-groups','record-review','annotation-task'])$(field).addEventListener(field==='annotation-task'||field==='record-review'?'change':'input',()=>{annotationDirty=true;annotationHelp();controls();});
  window.addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});
  window.addEventListener('tuldok-session',()=>{++epoch;busy=false;blocked=true;selectedContracts=new Set();controls();message('Session changed. Refreshing project status; your unsubmitted edits remain here.');refresh();});
  controls();refresh();
})();
