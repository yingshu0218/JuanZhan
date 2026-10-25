CREATE TABLE upload_policy (
 id INTEGER PRIMARY KEY CHECK(id=1),
 version INTEGER NOT NULL CHECK(version>=1),
 config_json TEXT NOT NULL CHECK(json_valid(config_json))
);
INSERT INTO upload_policy VALUES (1,1,'{"excluded_groups":["structured_data","developer_config","source_code","executables","archives","databases_logs","development_directories"],"custom_extensions":[]}');
